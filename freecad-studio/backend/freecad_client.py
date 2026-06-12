"""Bridge to FreeCAD MCP RPC server (same protocol MCP uses)."""
from __future__ import annotations

import threading
import xmlrpc.client
from typing import Any


class FreeCADClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9875,
        timeout: float = 30.0,
        health_timeout: float = 3.0,
    ):
        self.host = host
        self.port = port
        self._timeout = timeout
        self._health_timeout = health_timeout
        self._lock = threading.Lock()

    def _new_proxy(self, timeout: float) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(
            f"http://{self.host}:{self.port}",
            allow_none=True,
            transport=_TimeoutTransport(timeout),
        )

    def _rpc(self, method: str, *args, timeout: float | None = None, retries: int = 3) -> Any:
        """Thread-safe RPC with a fresh connection per attempt."""
        call_timeout = self._timeout if timeout is None else timeout
        last_error: Exception | None = None
        with self._lock:
            for _ in range(retries):
                proxy = self._new_proxy(call_timeout)
                try:
                    return getattr(proxy, method)(*args)
                except Exception as exc:
                    last_error = exc
                    continue
        if last_error:
            raise last_error
        return None

    def _ping_proxy(self, proxy: xmlrpc.client.ServerProxy) -> bool:
        try:
            return bool(proxy.ping())
        except Exception:
            return False

    def ping(self) -> bool:
        try:
            return bool(self._rpc("ping", timeout=self._timeout, retries=2))
        except Exception:
            return False

    def ping_health(self) -> bool:
        """Fast health check for status polling (short timeout, fresh connection)."""
        proxy = self._new_proxy(self._health_timeout)
        for _ in range(2):
            if self._ping_proxy(proxy):
                return True
            proxy = self._new_proxy(self._health_timeout)
        return False

    def execute_code(self, code: str) -> dict[str, Any]:
        try:
            result = self._rpc("execute_code", code, timeout=120.0, retries=2)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        return {"success": False, "error": "RPC call failed"}

    def create_document(self, name: str) -> dict[str, Any]:
        try:
            result = self._rpc("create_document", name)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        return {"success": False, "error": "RPC call failed"}

    def list_documents(self) -> list[str]:
        try:
            result = self._rpc("list_documents")
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        try:
            result = self._rpc("get_objects", doc_name)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def get_active_screenshot(self, view_name: str = "Isometric") -> dict[str, Any]:
        last_error = "Screenshot failed — switch FreeCAD to Part workbench with a 3D view open"
        try:
            result = self._rpc("get_active_screenshot", view_name, timeout=60.0, retries=3)
            if isinstance(result, str):
                image = result.strip()
                if image:
                    return {"success": True, "image": image}
                last_error = "FreeCAD returned an empty screenshot"
            elif isinstance(result, dict):
                if result.get("success") and result.get("image"):
                    return result
                last_error = result.get("error") or last_error
            elif result is None:
                last_error = "FreeCAD view does not support screenshots (use Part workbench 3D view)"
        except Exception as exc:
            last_error = f"Screenshot RPC error: {exc}"
        return {"success": False, "error": last_error}


class _TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn