"""Local HTTP + BlueZ bridge server for MiBuds Linux."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from controllers.bluetooth.redmi_buds_8_pro import RedmiBuds8ProService

ROOT_DIR = Path(__file__).resolve().parent
UI_DIR = ROOT_DIR / "web_ui"
ASSETS_DIR = ROOT_DIR / "assets"


def _safe_resolve(base_dir: Path, rel_path: str) -> Optional[Path]:
    candidate = (base_dir / rel_path).resolve()
    try:
        candidate.relative_to(base_dir.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


class _EarbudsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: RedmiBuds8ProService,
    ) -> None:
        self.service = service
        super().__init__(server_address, _RequestHandler)


class _RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        ctype, _ = mimetypes.guess_type(str(path))
        if not ctype:
            ctype = "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/state":
            self._send_json(HTTPStatus.OK, self.server.service.get_state())
            return

        if path == "/api/bluetooth/scan":
            devices = self.server.service.scan_bluetooth_devices()
            self._send_json(HTTPStatus.OK, {"devices": devices, "state": self.server.service.get_state()})
            return

        if path.startswith("/assets/"):
            rel = path[len("/assets/"):]
            target = _safe_resolve(ASSETS_DIR, rel)
            if target:
                self._send_file(target)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Asset not found"})
            return

        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = _safe_resolve(UI_DIR, rel)
        if target:
            self._send_file(target)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        svc: RedmiBuds8ProService = self.server.service

        try:
            body = self._read_json()

            if path == "/api/noise":
                state = svc.set_noise_control(
                    mode=body.get("mode"),
                    smart_anc=body.get("smart_anc"),
                    anc_level=body.get("anc_level"),
                    transparency_level=body.get("transparency_level"),
                )
            elif path == "/api/immersive-commute":
                state = svc.set_immersive_commute(
                    str(body.get("mode", "off")),
                    volume=body.get("volume"),
                )
            elif path == "/api/immersive-commute/volume":
                state = svc.set_immersive_commute_volume(int(body["volume"]))
            elif path == "/api/theme":
                state = svc.set_theme(
                    mode=body.get("mode"),
                    custom_base=body.get("custom_base"),
                    accent=body.get("accent"),
                    bg=body.get("bg"),
                    card=body.get("card"),
                    reset=bool(body.get("reset", False)),
                )
            elif path == "/api/gestures":
                state = svc.set_gesture(
                    str(body["gesture"]),
                    str(body["side"]),
                    str(body["action"]),
                )
            elif path == "/api/press-hold-modes":
                state = svc.set_press_hold_modes(
                    str(body["side"]),
                    list(body["modes"]),
                )
            elif path == "/api/audio-effects":
                state = svc.set_audio_effects(
                    spatial_audio=body.get("spatial_audio"),
                    head_tracking=body.get("head_tracking"),
                    spatial_scene=body.get("spatial_scene"),
                    eq_preset=body.get("eq_preset"),
                    adaptive_sound=body.get("adaptive_sound"),
                )
            elif path == "/api/additional-settings":
                state = svc.set_additional_settings(
                    in_ear_detection=body.get("in_ear_detection"),
                    dual_connection=body.get("dual_connection"),
                    auto_answer=body.get("auto_answer"),
                    adaptive_volume=body.get("adaptive_volume"),
                    color=body.get("color"),
                    show_case=body.get("show_case"),
                )
            elif path == "/api/find-earphones":
                state = svc.set_find_earphones(
                    str(body.get("target", "both")),
                    bool(body.get("active", False)),
                )
            elif path == "/api/wearing/refresh":
                state = svc.refresh_wearing_state()
            elif path == "/api/battery/refresh":
                state = svc.refresh_battery()
            elif path == "/api/bluetooth/connect":
                state = svc.connect_bluetooth(body.get("address"), device_name=body.get("name"))
            elif path == "/api/bluetooth/disconnect":
                state = svc.disconnect_bluetooth(manual=True)
            elif path == "/api/logs/clear":
                state = svc.clear_tx_log()
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint {path}"})
                return

            self._send_json(HTTPStatus.OK, state)
        except ConnectionError as exc:
            self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except (KeyError, TypeError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def start_background_server(
    host: str = "127.0.0.1",
    port: int = 0,
    service: Optional[RedmiBuds8ProService] = None,
) -> tuple[_EarbudsHTTPServer, threading.Thread, int]:
    """Start the HTTP server in a daemon thread and return (server, thread, bound_port)."""
    svc = service or RedmiBuds8ProService()
    httpd = _EarbudsHTTPServer((host, port), svc)
    bound_port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, bound_port


def main() -> None:
    parser = argparse.ArgumentParser(description="MiBuds Linux Backend Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-bt-scan", action="store_true")
    args = parser.parse_args()

    svc = RedmiBuds8ProService(enable_bluetooth_auto=not args.no_bt_scan)
    httpd = _EarbudsHTTPServer((args.host, args.port), svc)
    print(f"MiBuds Linux server listening on http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        svc.shutdown()
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
