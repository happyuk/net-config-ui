# app/services/router_api.py

import requests
from typing import Any, Dict, Optional


class RouterAPI:
    """
    Lightweight RESTCONF client for Cisco IOS-XR / 8000v.

    Features:
      - RESTCONF GET/PUT/PATCH/HEAD helpers
      - consistent error handling
      - built-in timeouts for GUI responsiveness
      - JSON/YANG-aware content types
      - ready to extend for NETCONF later
    """

    def __init__(self, host: str, username: str, password: str, verify_tls: bool = False):
        self.host = host.strip().strip("/")
        self.auth = (username, password)
        self.verify = verify_tls      # XR lab: usually False
        self.base = f"https://{self.host}/restconf"
        self.timeout = 5              # seconds: GUI safe

    # ============================================================
    # LOW-LEVEL REQUEST WRAPPER
    # ============================================================

    def _request(
        self,
        method: str,
        path: str = "",
        *,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Any] = None
    ) -> requests.Response:
        """
        Internal request wrapper. Handles:
          - URL joining
          - timeouts
          - TLS verification
          - authentication
          - friendly error messages
        """

        url = f"{self.base}/{path.lstrip('/')}" if path else f"{self.base}/data"
        hdr = headers or {}

        try:
            resp = requests.request(
                method=method.upper(),
                url=url,
                auth=self.auth,
                verify=self.verify,
                headers=hdr,
                json=json,
                timeout=self.timeout,
            )
            return resp

        except requests.exceptions.RequestException as e:
            # GUI friendly
            raise RuntimeError(f"RESTCONF {method} request failed: {e}")

    # ============================================================
    # BASIC ENDPOINT TESTING
    # ============================================================

    def head_data(self) -> requests.Response:
        """
        Fast connectivity check for RESTCONF:
        HEAD /restconf/data
        """
        return self._request("HEAD", "data")

    def get_root(self) -> requests.Response:
        """
        GET /restconf/data
        """
        return self._request(
            "GET",
            "data",
            headers={"Accept": "application/yang-data+json"},
        )

    # ============================================================
    # GENERIC RESTCONF HELPERS
    # ============================================================

    def get(self, path: str, accept_json: bool = True) -> requests.Response:
        """
        GET with optional JSON or XML YANG output.
        """
        content_type = (
            "application/yang-data+json" if accept_json else "application/yang-data+xml"
        )

        return self._request(
            "GET",
            f"data/{path}",
            headers={"Accept": content_type},
        )

    def put(self, path: str, payload_json: Dict[str, Any]) -> requests.Response:
        """
        PUT (create/replace config)
        """
        return self._request(
            "PUT",
            f"data/{path}",
            headers={"Content-Type": "application/yang-data+json"},
            json=payload_json,
        )

    def patch(self, path: str, payload_json: Dict[str, Any]) -> requests.Response:
        """
        PATCH (modify config using JSON)
        """
        return self._request(
            "PATCH",
            f"data/{path}",
            headers={"Content-Type": "application/yang-data+json"},
            json=payload_json,
        )

    def delete(self, path: str) -> requests.Response:
        """
        DELETE operation.
        """
        return self._request("DELETE", f"data/{path}")
    
    # In app/services/router_api.py

    # 1) (optional) during testing, increase timeout a bit
    # self.timeout = 5
    # Change to:
    # self.timeout = 15

    def get_native_hostname(self):
        """
        GET the IOS-XE native model root with a shallow depth so it's fast.
        """
        # append query to limit payload
        path = "Cisco-IOS-XE-native:native/hostname"
        return self._request(
            "GET",
            f"data/{path}",
            headers={"Accept": "application/yang-data+json"},
        )

    def get_yang_modules_state(self):
        """
        Try modules-state (RFC 7895 older) and yang-library (RFC 8525 newer).
        """
        # Try modules-state first
        r = self._request("GET", "data/ietf-yang-library:modules-state",
                        headers={"Accept": "application/yang-data+json"})
        if r.status_code == 404:
            # Try newer yang-library node
            r = self._request("GET", "data/ietf-yang-library:yang-library",
                            headers={"Accept": "application/yang-data+json"})
        return r

    def get_operations(self):
        """
        Some devices expose operations endpoint quickly.
        """
        return self._request("GET", "operations",
                            headers={"Accept": "application/yang-data+json"})

    def ping(self):
        """
        Robust connectivity: try quick endpoints in order and report the first that responds.
        HEAD can return misleading 404s, so we always also try GETs.
        """
        # 1) HEAD /restconf/data (fast but not always reliable)
        try:
            r = self.head_data()
            if r.status_code in (200, 204, 401, 403):
                return True, f"HEAD /restconf/data -> {r.status_code}"
        except Exception:
            pass  # continue probing

        # 2) GET a small subtree: IOS-XE native root, shallow
        try:
            r = self.get_native_hostname()
            if r.status_code in (200, 204, 401, 403):
                return True, f"GET native?depth=1 -> {r.status_code}"
        except Exception:
            pass

        # 3) GET YANG library (modules-state / yang-library)
        try:
            r = self.get_yang_modules_state()
            if r.status_code in (200, 204, 401, 403):
                return True, f"GET yang-library -> {r.status_code}"
        except Exception:
            pass

        # 4) GET operations
        try:
            r = self.get_operations()
            if r.status_code in (200, 204, 401, 403):
                return True, f"GET /restconf/operations -> {r.status_code}"
        except Exception as e:
            pass

        # 5) Last resort: GET /restconf/data (can be heavy)
        try:
            r = self.get_root()
            return (r.status_code in (200, 204, 401, 403),
                    f"GET /restconf/data -> {r.status_code}")
        except Exception as e:
            return False, f"RESTCONF probe failed: {e}"
