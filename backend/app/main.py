"""
FastAPI application entry point.

Run with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import settings
from app.core.events import EventBus, EventType, event_bus
from app.core.exceptions import BaseAppError
from app.core.logging import setup_logging
from app.db.redis import RedisClient
from app.db.session import async_session_factory, close_db, init_db
from app.exchanges.factory import ExchangeFactory
from app.services.alert_service import AlertService
from app.services.analytics import AnalyticsService
from app.services.audit import AuditService
from app.services.execution_coordinator import ExecutionCoordinator
from app.services.execution_engine import ExecutionEngine
from app.services.execution_planner import ExecutionPlanner
from app.services.inventory import InventoryManager
from app.services.market_data import MarketDataService
from app.services.risk_engine import RiskEngine
from app.services.scanner import ArbitrageScanner
from app.services.simulation import SimulationService

# Phase 6: Live trading safety
from app.core.credentials import CredentialManager
from app.core.kill_switch import KillSwitch
from app.services.live_guardrails import LiveGuardrails
from app.services.order_tracker import OrderTracker


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manages WebSocket connections grouped by channel."""

    def __init__(self) -> None:
        self._channels: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._channels.setdefault(channel, []).append(ws)
        logger.info("WS connected: channel={ch}, total={n}", ch=channel, n=len(self._channels.get(channel, [])))

    async def disconnect(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._channels.get(channel, [])
            if ws in conns:
                conns.remove(ws)
        logger.info("WS disconnected: channel={ch}", ch=channel)

    async def broadcast(self, channel: str, data: Any) -> None:
        conns = list(self._channels.get(channel, []))
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    ch_conns = self._channels.get(channel, [])
                    if ws in ch_conns:
                        ch_conns.remove(ws)

    @property
    def stats(self) -> dict[str, int]:
        return {ch: len(conns) for ch, conns in self._channels.items()}


ws_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Event bus -> WebSocket bridge
# ---------------------------------------------------------------------------

async def _bridge_event_to_ws(event_type: EventType, ws_channel: str) -> None:
    """Subscribe to an internal event type and forward payloads to all
    connected WebSocket clients on *ws_channel*."""

    async def _handler(event: Any) -> None:
        payload = {
            "type": event.type.value,
            "data": event.data,
            "id": event.id,
            "timestamp": event.timestamp,
        }
        await ws_manager.broadcast(ws_channel, payload)

    event_bus.subscribe(event_type, _handler)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""

    # ---- STARTUP ----------------------------------------------------------

    # 1. Setup logging
    setup_logging()
    logger.info(
        "Starting {name} v{ver} (paper_mode={pm})",
        name=settings.app_name,
        ver=settings.app_version,
        pm=settings.trading.paper_mode,
    )

    # 2. Init DB (create tables if needed)
    try:
        await init_db()
        logger.info("Database initialised")
    except Exception:
        logger.opt(exception=True).error("Failed to initialise database -- continuing without DB")

    # 3. Init Redis (graceful fallback if unavailable)
    redis_client = RedisClient()
    try:
        await redis_client.connect()
        app.state.redis = redis_client
        logger.info("Redis connected")
    except Exception:
        logger.opt(exception=True).error("Failed to connect to Redis -- continuing without cache")
        app.state.redis = None
        redis_client = None  # type: ignore[assignment]

    # 4. Create EventBus (use the module-level singleton)
    app.state.event_bus = event_bus

    # 4b. Create AuditService
    audit_service = AuditService(event_bus=event_bus)
    app.state.audit_service = audit_service
    logger.info("AuditService created")

    # 5. Create ExchangeFactory -> create adapters (mock in paper mode)
    exchange_factory = ExchangeFactory()
    exchange_factory.create_from_settings()
    app.state.exchange_factory = exchange_factory
    logger.info(
        "ExchangeFactory created with {} adapters: {}",
        len(exchange_factory.get_all()),
        list(exchange_factory.get_all().keys()),
    )

    # 6. Initialize all exchange adapters
    await exchange_factory.initialize_all()
    logger.info("All exchange adapters initialised")

    # 7. Create MarketDataService with adapters + event_bus + redis
    market_data = MarketDataService(
        event_bus=event_bus,
        exchange_factory=exchange_factory,
        redis_client=redis_client or RedisClient(),  # pass a dummy if redis is down
        config=settings,
    )
    app.state.market_data = market_data

    # 8. Start MarketDataService (subscribes to tickers/orderbooks)
    await market_data.start()
    logger.info("MarketDataService started")

    # 9. Create SimulationService
    simulation = SimulationService(
        market_data=market_data,
        exchange_factory=exchange_factory,
        config=settings,
    )
    app.state.simulation = simulation
    logger.info("SimulationService created")

    # 10. Create ArbitrageScanner with market_data + adapters + event_bus
    scanner = ArbitrageScanner(
        market_data=market_data,
        exchange_factory=exchange_factory,
        event_bus=event_bus,
        config=settings,
    )
    app.state.scanner = scanner

    # 11. Start ArbitrageScanner background loop
    await scanner.start()
    logger.info("ArbitrageScanner started")

    # 11b. Create RiskEngine
    redis_for_services = redis_client or RedisClient()
    risk_engine = RiskEngine(
        event_bus=event_bus,
        redis_client=redis_for_services,
        session_factory=async_session_factory,
        market_data=market_data,
        config=settings,
    )
    app.state.risk_engine = risk_engine
    logger.info("RiskEngine created")

    # 11c. Create InventoryManager
    inventory_manager = InventoryManager(
        event_bus=event_bus,
        exchange_factory=exchange_factory,
        redis_client=redis_for_services,
        session_factory=async_session_factory,
        market_data=market_data,
        config=settings,
    )
    app.state.inventory_manager = inventory_manager
    logger.info("InventoryManager created")

    # 11d. Create AlertService
    alert_service = AlertService(
        event_bus=event_bus,
        redis_client=redis_for_services,
        session_factory=async_session_factory,
        market_data=market_data,
        exchange_factory=exchange_factory,
        config=settings,
    )
    app.state.alert_service = alert_service
    logger.info("AlertService created")

    # 11e. Create AnalyticsService
    analytics_service = AnalyticsService(
        session_factory=async_session_factory,
        config=settings,
    )
    app.state.analytics_service = analytics_service
    logger.info("AnalyticsService created")

    # 11f. Create ExecutionEngine
    execution_engine = ExecutionEngine(
        event_bus=event_bus,
        exchange_factory=exchange_factory,
        redis_client=redis_for_services,
        session_factory=async_session_factory,
        risk_engine=risk_engine,
        simulation_service=simulation,
        config=settings,
    )
    app.state.execution_engine = execution_engine
    logger.info("ExecutionEngine created")

    # 11g. Create ExecutionPlanner
    execution_planner = ExecutionPlanner(
        risk_engine=risk_engine,
        inventory_manager=inventory_manager,
        market_data=market_data,
        simulation_service=simulation,
    )
    app.state.execution_planner = execution_planner
    logger.info("ExecutionPlanner created")

    # 11h. Create ExecutionCoordinator
    coordinator = ExecutionCoordinator(
        execution_engine=execution_engine,
        risk_engine=risk_engine,
        inventory_manager=inventory_manager,
        alert_service=alert_service,
        audit_service=audit_service,
        analytics_service=analytics_service,
        event_bus=event_bus,
        execution_planner=execution_planner,
    )
    app.state.coordinator = coordinator
    logger.info("ExecutionCoordinator created")

    # 12. Phase 6: Live trading safety infrastructure
    # 12a. Credential Manager
    credential_manager = CredentialManager()
    credential_manager.load_from_env()
    app.state.credential_manager = credential_manager
    logger.info(
        "CredentialManager loaded: {} exchanges with keys",
        sum(1 for c in credential_manager.get_all().values() if c.has_keys),
    )

    # 12b. Kill Switch
    kill_switch = KillSwitch()
    app.state.kill_switch = kill_switch
    logger.info("KillSwitch created")

    # 12c. Live Guardrails
    live_guardrails = LiveGuardrails(
        kill_switch=kill_switch,
        credential_manager=credential_manager,
        event_bus=event_bus,
        redis_client=redis_for_services,
        audit_service=audit_service,
        market_data=market_data,
        config=settings,
    )
    app.state.live_guardrails = live_guardrails
    logger.info("LiveGuardrails created (mode={})", live_guardrails.current_mode.value)

    # 12d. Order Tracker
    order_tracker = OrderTracker(
        event_bus=event_bus,
        exchange_factory=exchange_factory,
        config=settings,
    )
    app.state.order_tracker = order_tracker
    await order_tracker.start()
    logger.info("OrderTracker started")

    # 13. Wire event bus to WebSocket bridge
    await _bridge_event_to_ws(EventType.MARKET_UPDATE, "market")
    await _bridge_event_to_ws(EventType.OPPORTUNITY_FOUND, "opportunities")
    await _bridge_event_to_ws(EventType.OPPORTUNITY_EXPIRED, "opportunities")
    await _bridge_event_to_ws(EventType.EXECUTION_STARTED, "executions")
    await _bridge_event_to_ws(EventType.EXECUTION_COMPLETED, "executions")
    await _bridge_event_to_ws(EventType.EXECUTION_FAILED, "executions")
    await _bridge_event_to_ws(EventType.RISK_VIOLATION, "alerts")
    await _bridge_event_to_ws(EventType.ALERT_TRIGGERED, "alerts")
    await _bridge_event_to_ws(EventType.BALANCE_UPDATED, "market")
    await _bridge_event_to_ws(EventType.SYSTEM_EVENT, "alerts")
    # Live trading events
    await _bridge_event_to_ws(EventType.KILL_SWITCH_ACTIVATED, "alerts")
    await _bridge_event_to_ws(EventType.KILL_SWITCH_RELEASED, "alerts")
    await _bridge_event_to_ws(EventType.CIRCUIT_BREAKER_OPENED, "alerts")
    await _bridge_event_to_ws(EventType.CIRCUIT_BREAKER_RESET, "alerts")
    await _bridge_event_to_ws(EventType.LIVE_ORDER_SUBMITTED, "executions")
    await _bridge_event_to_ws(EventType.LIVE_ORDER_FILLED, "executions")
    await _bridge_event_to_ws(EventType.LIVE_ORDER_FAILED, "executions")
    await _bridge_event_to_ws(EventType.LIVE_MODE_CHANGED, "alerts")
    await _bridge_event_to_ws(EventType.RECONCILIATION_MISMATCH, "alerts")

    # 13. Publish a system-ready event
    await event_bus.publish(EventType.SYSTEM_EVENT, {"status": "started", "paper_mode": settings.trading.paper_mode})

    logger.info("Application startup complete")

    # ---- YIELD (app is running) -------------------------------------------
    yield

    # ---- SHUTDOWN ---------------------------------------------------------
    logger.info("Shutting down...")

    await event_bus.publish(EventType.SYSTEM_EVENT, {"status": "shutting_down"})

    # Stop order tracker
    await order_tracker.stop()
    logger.info("OrderTracker stopped")

    # Stop scanner
    await scanner.stop()
    logger.info("ArbitrageScanner stopped")

    # Stop market data
    await market_data.stop()
    logger.info("MarketDataService stopped")

    # Shutdown exchanges
    await exchange_factory.shutdown_all()
    logger.info("Exchange adapters shut down")

    event_bus.unsubscribe_all()

    # Close redis
    if app.state.redis:
        await app.state.redis.disconnect()
        logger.info("Redis disconnected")

    # Close DB
    await close_db()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Crypto Arbitrage API",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(BaseAppError)
async def app_error_handler(_request: Request, exc: BaseAppError) -> JSONResponse:
    logger.warning("AppError {code}: {msg}", code=exc.code.name, msg=exc.message)
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


@app.exception_handler(Exception)
async def generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.opt(exception=True).error("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "code": 1000,
            "code_name": "UNKNOWN",
            "message": "Internal server error",
            "details": {},
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/", tags=["health"])
async def root():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "paper_mode": settings.trading.paper_mode,
        "timestamp": time.time(),
    }


@app.get("/health", tags=["health"])
async def health(request: Request):
    redis_ok = False
    if getattr(request.app.state, "redis", None):
        try:
            await request.app.state.redis.client.ping()
            redis_ok = True
        except Exception:
            pass

    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis": redis_ok,
        "websocket_connections": ws_manager.stats,
        "event_bus_subscribers": event_bus.subscriber_counts,
    }


# ---------------------------------------------------------------------------
# API routers (mounted lazily -- each router module is optional)
# ---------------------------------------------------------------------------

def _mount_routers() -> None:
    """Try to import and mount each API router. Missing modules are silently
    skipped so the core framework runs even before route modules exist."""

    router_modules = [
        # New comprehensive route modules (prefix baked into each router)
        ("app.api.routes.system", "", ["system"]),
        ("app.api.routes.market", "", ["market"]),
        ("app.api.routes.strategies", "", ["strategies"]),
        ("app.api.routes.executions", "", ["executions"]),
        ("app.api.routes.orders", "", ["orders"]),
        ("app.api.routes.risk", "", ["risk"]),
        ("app.api.routes.inventory", "", ["inventory"]),
        ("app.api.routes.analytics", "", ["analytics"]),
        ("app.api.routes.alerts", "", ["alerts"]),
        ("app.api.routes.audit", "", ["audit"]),
        # New routes
        ("app.api.routes.simulate", "", ["simulate"]),
        ("app.api.routes.exchanges", "", ["exchanges"]),
        ("app.api.routes.scanner_status", "", ["scanner"]),
        # Phase 6: Live trading
        ("app.api.routes.live", "", ["live"]),
        ("app.api.routes.kill_switch", "", ["kill-switch"]),
    ]

    import importlib

    for module_path, prefix, tags in router_modules:
        try:
            mod = importlib.import_module(module_path)
            router = getattr(mod, "router", None)
            if router:
                app.include_router(router, prefix=prefix, tags=tags)
                logger.info("Mounted router: {mod}", mod=module_path)
        except ImportError:
            logger.debug("Router module {mod} not found -- skipping", mod=module_path)


_mount_routers()


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------

async def _ws_loop(ws: WebSocket, channel: str) -> None:
    """Generic WebSocket handler: accept, keep-alive, disconnect."""
    await ws_manager.connect(channel, ws)
    try:
        while True:
            # We expect clients to send pings/keep-alives; we just read and
            # discard.  Data flows server -> client via broadcast.
            data = await ws.receive_text()
            # Clients can send a JSON ping; we reply with pong.
            if data.strip().lower() in ('ping', '{"type":"ping"}'):
                await ws.send_json({"type": "pong", "timestamp": time.time()})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.opt(exception=True).debug("WS error on channel={ch}", ch=channel)
    finally:
        await ws_manager.disconnect(channel, ws)


@app.websocket("/ws/market")
async def ws_market(ws: WebSocket):
    """Real-time market data (prices, balances)."""
    await _ws_loop(ws, "market")


@app.websocket("/ws/opportunities")
async def ws_opportunities(ws: WebSocket):
    """Arbitrage opportunity stream."""
    await _ws_loop(ws, "opportunities")


@app.websocket("/ws/executions")
async def ws_executions(ws: WebSocket):
    """Trade execution updates."""
    await _ws_loop(ws, "executions")


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    """System alerts, risk violations, status changes."""
    await _ws_loop(ws, "alerts")
