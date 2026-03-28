"""
Service layer for the crypto arbitrage system.

All services are async, accept dependencies via constructor, and are
designed to run as background tasks started from the main.py lifespan.
"""

from app.services.market_data import MarketDataService
from app.services.scanner import ArbitrageScanner, CrossExchangeScanner, TriangularScanner
from app.services.risk_engine import RiskEngine
from app.services.execution_engine import ExecutionEngine
from app.services.simulation import SimulationService
from app.services.inventory import InventoryManager
from app.services.analytics import AnalyticsService
from app.services.alert_service import AlertService

__all__ = [
    "MarketDataService",
    "ArbitrageScanner",
    "CrossExchangeScanner",
    "TriangularScanner",
    "RiskEngine",
    "ExecutionEngine",
    "SimulationService",
    "InventoryManager",
    "AnalyticsService",
    "AlertService",
]
