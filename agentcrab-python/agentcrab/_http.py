"""Sync HTTP transport with auto-auth and error mapping."""

from __future__ import annotations

import warnings
from typing import Any

import httpx

from ._auth import build_auth_headers, build_l2_headers
from ._exceptions import (
    APIError,
    AuthError,
    InsufficientBalance,
    NetworkError,
    OrderError,
    PaymentError,
)

_version_warning_shown = False


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse version string to tuple for comparison."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)

# Map server error_code to exception class
_ERROR_MAP: dict[str, type] = {
    "INVALID_SIGNATURE": AuthError,
    "MISSING_TX_HASH": PaymentError,
    "PAYMENT_NOT_VERIFIED": PaymentError,
    "INSUFFICIENT_BALANCE": InsufficientBalance,
    "BALANCE_DEDUCTION_FAILED": PaymentError,
    "INVALID_PAYMENT_MODE": PaymentError,
    "ORDER_REJECTED": OrderError,
    "ORDER_ERROR": OrderError,
    "ORDER_BUILD_FAILED": OrderError,
}


class HttpTransport:
    """Sync HTTP client with auto-injected auth headers."""

    def __init__(
        self,
        base_url: str,
        private_key: str,
        address: str,
        payment_mode: str = "prepaid",
        timeout: float = 60.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._private_key = private_key
        self._address = address
        self._payment_mode = payment_mode
        from . import __version__
        self._sdk_version = __version__
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers={"X-SDK-Version": self._sdk_version},
        )

    def close(self) -> None:
        self._client.close()
        # Clear private key from memory to minimize exposure window
        self._private_key = ""

    def _check_version(self, resp: httpx.Response) -> None:
        """Check X-Min-SDK-Version header and warn if SDK is outdated."""
        global _version_warning_shown
        if _version_warning_shown:
            return
        min_ver = resp.headers.get("x-min-sdk-version")
        if not min_ver:
            return
        if _parse_version(self._sdk_version) < _parse_version(min_ver):
            _version_warning_shown = True
            warnings.warn(
                f"agentcrab SDK outdated ({self._sdk_version} < {min_ver}). "
                f"Run: pip install --upgrade agentcrab",
                stacklevel=3,
            )

    def _auth_headers(self) -> dict[str, str]:
        return build_auth_headers(self._private_key, self._address, self._payment_mode)

    def _raise_for_error(self, resp: httpx.Response) -> None:
        """Parse server error response and raise typed exception."""
        if resp.status_code < 400:
            return
        try:
            body = resp.json()
            # Handle FastAPI's HTTPException detail format
            if isinstance(body, dict):
                detail = body if "error_code" in body else body.get("detail", body)
            else:
                detail = body
            if isinstance(detail, dict):
                error_code = detail.get("error_code", "")
                message = detail.get("message", resp.text)
            else:
                error_code = ""
                message = str(detail) if detail else resp.text
        except Exception:
            error_code = ""
            message = resp.text

        exc_cls = _ERROR_MAP.get(error_code, APIError)
        raise exc_cls(message=message, error_code=error_code, status_code=resp.status_code)

    def get(
        self,
        path: str,
        params: dict | None = None,
        auth: bool = True,
        paid: bool = False,
        l2_creds: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Send GET request. Returns parsed JSON body."""
        headers = self._auth_headers() if (auth or paid) else {}
        if l2_creds:
            headers.update(build_l2_headers(**l2_creds))
        try:
            kwargs: dict = {"params": params, "headers": headers}
            if timeout is not None:
                kwargs["timeout"] = timeout
            resp = self._client.get(path, **kwargs)
        except httpx.HTTPError as e:
            raise NetworkError(message=str(e)) from e
        self._check_version(resp)
        self._raise_for_error(resp)
        try:
            return resp.json()
        except ValueError as e:
            raise NetworkError(message=f"Invalid JSON response: {e}") from e

    def post(
        self,
        path: str,
        json: Any = None,
        auth: bool = True,
        paid: bool = False,
        l2_creds: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Send POST request. Returns parsed JSON body."""
        headers = self._auth_headers() if (auth or paid) else {}
        if l2_creds:
            headers.update(build_l2_headers(**l2_creds))
        try:
            kwargs: dict = {"json": json, "headers": headers}
            if timeout is not None:
                kwargs["timeout"] = timeout
            resp = self._client.post(path, **kwargs)
        except httpx.HTTPError as e:
            raise NetworkError(message=str(e)) from e
        self._check_version(resp)
        self._raise_for_error(resp)
        try:
            return resp.json()
        except ValueError as e:
            raise NetworkError(message=f"Invalid JSON response: {e}") from e

    def delete(
        self,
        path: str,
        params: dict | None = None,
        json: Any = None,
        auth: bool = True,
        paid: bool = False,
        l2_creds: dict | None = None,
    ) -> Any:
        """Send DELETE request. Returns parsed JSON body."""
        headers = self._auth_headers() if (auth or paid) else {}
        if l2_creds:
            headers.update(build_l2_headers(**l2_creds))
        try:
            resp = self._client.request("DELETE", path, params=params, json=json, headers=headers)
        except httpx.HTTPError as e:
            raise NetworkError(message=str(e)) from e
        self._check_version(resp)
        self._raise_for_error(resp)
        try:
            return resp.json()
        except ValueError as e:
            raise NetworkError(message=f"Invalid JSON response: {e}") from e


def _extract_data(resp: dict) -> Any:
    """Extract ``data`` field from SuccessResponse envelope."""
    return resp.get("data", resp)
