import os
import re


EDITION = os.getenv("PANEL_EDITION", "core").strip().lower()
if EDITION not in {"core", "easy"}:
    raise RuntimeError("PANEL_EDITION must be core or easy")
IS_EASY = EDITION == "easy"
PRODUCT_NAME = "3WG Easy Core" if IS_EASY else "3WG Core"

EASY_PAGES = {
    "/", "/ui", "/login", "/settings", "/status", "/apikeys", "/monitoring",
    "/abuse", "/updates", "/backups",
}


def easy_page_allowed(path):
    return path in EASY_PAGES or bool(re.fullmatch(
        r"/client/\d+|/status/(wireguard|amneziawg)", path
    ))


def easy_route_allowed(path):
    if path in {"/health", "/metrics", "/protocol-health", "/logout"}:
        return True
    if path.startswith("/api/"):
        if path == "/api/backups/auto":
            return False
        return any(path == prefix or path.startswith(prefix + "/") for prefix in (
            "/api/auth", "/api/version", "/api/update", "/api/peers",
            "/api/categories", "/api/dashboard", "/api/ui/dashboard",
            "/api/node/protocols", "/api/node/status", "/api/backups",
            "/api/apikeys", "/api/monitoring", "/api/telegram", "/api/p2p-guard",
        ))
    return path in {
        "/client/{client_id}/download", "/client/{client_id}/download-vpn",
        "/client/{client_id}/qr/native", "/client/{client_id}/qr/amnezia-vpn",
        "/client/{client_id}/qr/native/download",
        "/client/{client_id}/qr/amnezia-vpn/download",
    }
