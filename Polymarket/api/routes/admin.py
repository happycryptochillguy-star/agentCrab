"""Admin endpoints — health status, manual health check, config hot reload.

All endpoints require X-Admin-Key header matching the ADMIN_KEY env var.
These are registered at root level (/admin/*), NOT under /polymarket.
"""

import hmac as _hmac

from fastapi import APIRouter, Depends, Header, HTTPException

from api.config import settings, reload_settings
from api.models import SuccessResponse, ErrorResponse
from api.services import health as health_svc

router = APIRouter(prefix="/admin", tags=["admin"])


async def _verify_admin(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """Verify admin key from header."""
    if not settings.admin_key:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error_code="ADMIN_NOT_CONFIGURED",
                message="Admin key not configured on server. Set ADMIN_KEY in .env.",
            ).model_dump(),
        )
    if not _hmac.compare_digest(x_admin_key, settings.admin_key):
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(
                error_code="INVALID_ADMIN_KEY",
                message="Invalid admin key.",
            ).model_dump(),
        )


@router.get("/health-status")
async def get_health_status(
    _: None = Depends(_verify_admin),
):
    """Get current health status of all external dependencies.

    Returns the latest probe results from the background health check loop.
    """
    states = health_svc.get_all_states()

    if not states:
        return SuccessResponse(
            summary="No health data yet. Probes start 30s after server boot.",
            data={"probes": {}, "summary": {"ok": 0, "fail": 0, "unknown": 0}},
        )

    ok = sum(1 for s in states.values() if s["status"] == "ok")
    fail = sum(1 for s in states.values() if s["status"] == "fail")
    unknown = sum(1 for s in states.values() if s["status"] == "unknown")

    summary_text = f"Health: {ok}/{len(states)} OK"
    if fail:
        summary_text += f", {fail} FAILING"
        failed_names = [s["label"] for s in states.values() if s["status"] == "fail"]
        summary_text += f" ({', '.join(failed_names)})"
    if unknown:
        summary_text += f", {unknown} pending"

    return SuccessResponse(
        summary=summary_text,
        data={
            "probes": states,
            "summary": {"ok": ok, "fail": fail, "unknown": unknown, "total": len(states)},
        },
    )


@router.post("/health-check")
async def trigger_health_check(
    _: None = Depends(_verify_admin),
):
    """Manually trigger all health probes immediately.

    Runs all probes and returns results. Also updates state and may send alerts.
    """
    results = await health_svc.run_all_probes()

    ok = sum(1 for r in results.values() if r["status"] == "ok")
    fail = sum(1 for r in results.values() if r["status"] == "fail")

    summary_text = f"Health check complete: {ok}/{len(results)} OK"
    if fail:
        summary_text += f", {fail} FAILING"
        failed_names = [r["label"] for r in results.values() if r["status"] == "fail"]
        summary_text += f" ({', '.join(failed_names)})"

    return SuccessResponse(summary=summary_text, data=results)


@router.post("/reload-config")
async def reload_config(
    _: None = Depends(_verify_admin),
):
    """Hot reload configuration from .env without restarting the server.

    Re-reads all fields from .env and updates the running config in-place.
    Returns which fields changed (sensitive values are masked).
    """
    changes = reload_settings()

    if not changes:
        return SuccessResponse(
            summary="No configuration changes detected in .env.",
            data={"changed_fields": [], "details": {}},
        )

    # Mask sensitive values in the response
    sensitive = {
        "private_key", "admin_key", "telegram_bot_token",
        "poly_builder_api_key", "poly_builder_secret", "poly_builder_passphrase",
        "fun_xyz_api_key", "fun_xyz_api_url",
        "bsc_rpc_url", "polygon_rpc_url",  # contain Alchemy API key
        "relayer_url", "bridge_api_url",
        "bark_url",
        "l2_encryption_key", "l2_encryption_key_old",
    }

    safe_changes: dict[str, dict] = {}
    for field, (old, new) in changes.items():
        if field in sensitive:
            safe_changes[field] = {
                "old": "***" if old else "(empty)",
                "new": "***" if new else "(empty)",
            }
        else:
            safe_changes[field] = {"old": str(old), "new": str(new)}

    return SuccessResponse(
        summary=f"{len(changes)} config field(s) updated from .env: {', '.join(changes.keys())}",
        data={"changed_fields": list(changes.keys()), "details": safe_changes},
    )
