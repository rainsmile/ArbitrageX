"""
Scanner status and control endpoints -- monitor and trigger the arbitrage scanner.

Router prefix: /api/scanner
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_scanner(request: Request):
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        raise HTTPException(status_code=503, detail="ArbitrageScanner is not initialized")
    return scanner


def _metrics_to_dict(metrics) -> dict[str, Any]:
    """Convert a ScanMetrics dataclass to a JSON-serializable dict."""
    return {
        "total_scans": metrics.total_scans,
        "total_opportunities_found": metrics.total_opportunities_found,
        "last_scan_duration_ms": round(metrics.last_scan_duration_ms, 2),
        "avg_scan_duration_ms": round(metrics.avg_scan_duration_ms, 2),
        "last_scan_at": metrics.last_scan_at,
        "last_scan_age_s": round(time.time() - metrics.last_scan_at, 2) if metrics.last_scan_at > 0 else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/status",
    summary="Scanner status and metrics",
)
async def scanner_status(request: Request) -> dict[str, Any]:
    """Return the current status and performance metrics of the arbitrage scanner."""
    scanner = _get_scanner(request)

    all_metrics = scanner.metrics  # dict[str, ScanMetrics]

    cross_running = getattr(scanner.cross_exchange, "_running", False)
    tri_running = getattr(scanner.triangular, "_running", False)

    cross_metrics = _metrics_to_dict(all_metrics.get("cross_exchange", scanner.cross_exchange.metrics))
    tri_metrics = _metrics_to_dict(all_metrics.get("triangular", scanner.triangular.metrics))

    total_scans = cross_metrics["total_scans"] + tri_metrics["total_scans"]
    total_opps = cross_metrics["total_opportunities_found"] + tri_metrics["total_opportunities_found"]

    return {
        "is_running": cross_running or tri_running,
        "cross_exchange_scanner": {
            "running": cross_running,
            "metrics": cross_metrics,
        },
        "triangular_scanner": {
            "running": tri_running,
            "metrics": tri_metrics,
        },
        "summary": {
            "total_scans": total_scans,
            "total_opportunities_found": total_opps,
        },
        "timestamp": time.time(),
    }


@router.get(
    "/opportunities",
    summary="Current in-memory opportunities from latest scan",
)
async def scanner_opportunities(request: Request) -> dict[str, Any]:
    """Run a fresh scan and return all currently detected opportunities.

    This is more real-time than querying the database because it reflects
    the very latest market data.
    """
    scanner = _get_scanner(request)

    t0 = time.time()

    # Run both scanners once to get the freshest results
    cross_opps = []
    tri_opps = []
    try:
        cross_opps = await scanner.cross_exchange.scan_once()
    except Exception as exc:
        logger.warning("Cross-exchange scan failed: {}", exc)

    try:
        tri_opps = await scanner.triangular.scan_once()
    except Exception as exc:
        logger.warning("Triangular scan failed: {}", exc)

    all_opps = cross_opps + tri_opps
    elapsed_ms = (time.time() - t0) * 1000.0

    items = [opp.to_dict() for opp in all_opps]

    return {
        "scan_duration_ms": round(elapsed_ms, 2),
        "cross_exchange_count": len(cross_opps),
        "triangular_count": len(tri_opps),
        "total": len(items),
        "opportunities": items,
        "timestamp": time.time(),
    }


@router.post(
    "/trigger",
    summary="Manually trigger one scan cycle",
)
async def trigger_scan(request: Request) -> dict[str, Any]:
    """Manually trigger a single scan cycle and return results immediately.

    Useful for debugging, testing, and on-demand scanning.
    """
    scanner = _get_scanner(request)

    t0 = time.time()

    cross_opps = []
    tri_opps = []
    cross_error = None
    tri_error = None

    try:
        cross_opps = await scanner.cross_exchange.scan_once()
    except Exception as exc:
        cross_error = str(exc)
        logger.warning("Manual cross-exchange scan failed: {}", exc)

    try:
        tri_opps = await scanner.triangular.scan_once()
    except Exception as exc:
        tri_error = str(exc)
        logger.warning("Manual triangular scan failed: {}", exc)

    all_opps = cross_opps + tri_opps
    elapsed_ms = (time.time() - t0) * 1000.0

    items = [opp.to_dict() for opp in all_opps]

    # Get updated metrics
    cross_metrics = _metrics_to_dict(scanner.cross_exchange.metrics)
    tri_metrics = _metrics_to_dict(scanner.triangular.metrics)

    result: dict[str, Any] = {
        "triggered_at": t0,
        "scan_duration_ms": round(elapsed_ms, 2),
        "cross_exchange": {
            "found": len(cross_opps),
            "error": cross_error,
            "metrics": cross_metrics,
        },
        "triangular": {
            "found": len(tri_opps),
            "error": tri_error,
            "metrics": tri_metrics,
        },
        "total_found": len(items),
        "opportunities": items,
        "timestamp": time.time(),
    }

    return result
