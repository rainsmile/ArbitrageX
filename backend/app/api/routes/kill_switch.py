"""
Kill switch and circuit breaker API routes.

Endpoints for emergency stop, circuit breaker management,
and safety system status.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter(prefix="/api/risk/kill-switch", tags=["kill-switch"])


@router.get("/status")
async def get_kill_switch_status(request: Request) -> dict[str, Any]:
    """Get kill switch and all circuit breaker status."""
    kill_switch = getattr(request.app.state, "kill_switch", None)
    if not kill_switch:
        return {
            "kill_switch": {"active": False},
            "circuit_breakers": [],
            "message": "Kill switch not initialized",
        }

    ks_status = kill_switch.get_status()
    all_breakers = kill_switch.get_all_breakers()
    open_breakers = kill_switch.get_open_breakers()

    return {
        "kill_switch": ks_status,
        "circuit_breakers": {
            "total": len(all_breakers),
            "open": len(open_breakers),
            "breakers": [
                {
                    "scope": b.scope,
                    "is_open": b.is_open,
                    "failure_count": b.failure_count,
                    "failure_threshold": b.failure_threshold,
                    "opened_at": b.opened_at,
                    "auto_reset_after_s": b.auto_reset_after_s,
                    "last_failure_reason": b.last_failure_reason,
                }
                for b in all_breakers
            ],
        },
    }


@router.post("/activate")
async def activate_kill_switch(request: Request) -> dict[str, Any]:
    """Activate the global kill switch - halts ALL trading immediately.

    Body: {"reason": "manual emergency stop", "activated_by": "admin"}
    """
    body = await request.json()
    reason = body.get("reason", "manual activation via API")
    activated_by = body.get("activated_by", "api")

    kill_switch = getattr(request.app.state, "kill_switch", None)
    if not kill_switch:
        return JSONResponse(
            status_code=503, content={"error": "Kill switch not initialized"}
        )

    kill_switch.activate(reason=reason, activated_by=activated_by)

    # Publish event
    event_bus = getattr(request.app.state, "event_bus", None)
    if event_bus:
        from app.core.events import EventType

        await event_bus.publish(
            EventType.KILL_SWITCH_ACTIVATED,
            {
                "reason": reason,
                "activated_by": activated_by,
            },
        )

    logger.critical(
        "KILL SWITCH ACTIVATED via API by {} reason={}", activated_by, reason
    )

    return {
        "success": True,
        "kill_switch_active": True,
        "reason": reason,
        "activated_by": activated_by,
        "message": "Kill switch activated - ALL trading halted",
    }


@router.post("/release")
async def release_kill_switch(request: Request) -> dict[str, Any]:
    """Release the global kill switch - re-enables trading.

    Body: {"released_by": "admin", "confirm": true}
    """
    body = await request.json()
    released_by = body.get("released_by", "api")
    confirm = body.get("confirm", False)

    if not confirm:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Kill switch release requires explicit confirmation",
                "hint": "Add 'confirm': true to the request body",
            },
        )

    kill_switch = getattr(request.app.state, "kill_switch", None)
    if not kill_switch:
        return JSONResponse(
            status_code=503, content={"error": "Kill switch not initialized"}
        )

    if not kill_switch.is_active:
        return {"success": True, "message": "Kill switch was not active"}

    kill_switch.release(released_by=released_by)

    event_bus = getattr(request.app.state, "event_bus", None)
    if event_bus:
        from app.core.events import EventType

        await event_bus.publish(
            EventType.KILL_SWITCH_RELEASED,
            {
                "released_by": released_by,
            },
        )

    logger.warning("Kill switch RELEASED via API by {}", released_by)

    return {
        "success": True,
        "kill_switch_active": False,
        "released_by": released_by,
        "message": "Kill switch released - trading re-enabled",
    }


@router.get("/circuit-breakers")
async def list_circuit_breakers(request: Request) -> dict[str, Any]:
    """List all circuit breakers and their status."""
    kill_switch = getattr(request.app.state, "kill_switch", None)
    if not kill_switch:
        return {"breakers": []}

    all_breakers = kill_switch.get_all_breakers()
    return {
        "breakers": [
            {
                "scope": b.scope,
                "is_open": b.is_open,
                "failure_count": b.failure_count,
                "failure_threshold": b.failure_threshold,
                "opened_at": b.opened_at,
                "auto_reset_after_s": b.auto_reset_after_s,
                "should_auto_reset": b.should_auto_reset if b.is_open else False,
                "last_failure_reason": b.last_failure_reason,
            }
            for b in all_breakers
        ],
        "summary": {
            "total": len(all_breakers),
            "open": sum(1 for b in all_breakers if b.is_open),
            "closed": sum(1 for b in all_breakers if not b.is_open),
        },
    }


@router.post("/circuit-breakers/{scope}/reset")
async def reset_circuit_breaker(request: Request, scope: str) -> dict[str, Any]:
    """Manually reset a specific circuit breaker.

    Scope format: "exchange:binance", "symbol:BTC/USDT", "strategy:cross_exchange"
    """
    kill_switch = getattr(request.app.state, "kill_switch", None)
    if not kill_switch:
        return JSONResponse(
            status_code=503, content={"error": "Kill switch not initialized"}
        )

    # URL-decode scope (colons may be encoded)
    scope = unquote(scope)

    kill_switch.reset_breaker(scope)

    event_bus = getattr(request.app.state, "event_bus", None)
    if event_bus:
        from app.core.events import EventType

        await event_bus.publish(
            EventType.CIRCUIT_BREAKER_RESET, {"scope": scope, "manual": True}
        )

    logger.info("Circuit breaker manually reset: scope={}", scope)

    return {
        "success": True,
        "scope": scope,
        "message": f"Circuit breaker for '{scope}' has been reset",
    }


@router.post("/circuit-breakers/{scope}/trip")
async def trip_circuit_breaker(request: Request, scope: str) -> dict[str, Any]:
    """Manually trip (open) a circuit breaker for testing or emergency isolation.

    Body: {"reason": "manual isolation", "threshold": 5, "auto_reset_s": 300}
    """
    body = await request.json()
    reason = body.get("reason", "manual trip via API")
    auto_reset_s = body.get("auto_reset_s", 300.0)

    kill_switch = getattr(request.app.state, "kill_switch", None)
    if not kill_switch:
        return JSONResponse(
            status_code=503, content={"error": "Kill switch not initialized"}
        )

    scope = unquote(scope)

    # Create breaker with threshold=1 so one failure trips it
    kill_switch.get_or_create_breaker(scope, threshold=1, auto_reset_s=auto_reset_s)
    tripped = kill_switch.record_failure(scope, reason)

    event_bus = getattr(request.app.state, "event_bus", None)
    if event_bus:
        from app.core.events import EventType

        await event_bus.publish(
            EventType.CIRCUIT_BREAKER_OPENED,
            {
                "scope": scope,
                "reason": reason,
                "manual": True,
            },
        )

    return {
        "success": True,
        "scope": scope,
        "tripped": tripped,
        "reason": reason,
        "message": f"Circuit breaker for '{scope}' tripped",
    }


@router.get("/credentials")
async def get_credential_status(request: Request) -> dict[str, Any]:
    """Get credential status for all configured exchanges (never exposes secrets)."""
    cred_manager = getattr(request.app.state, "credential_manager", None)
    if not cred_manager:
        return {"credentials": [], "message": "Credential manager not initialized"}

    creds = cred_manager.get_all()
    return {
        "credentials": [c.to_safe_dict() for c in creds.values()],
        "total": len(creds),
        "with_keys": sum(1 for c in creds.values() if c.has_keys),
    }
