"""Small loopback-only HTTP API and bundled offline dashboard."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from attain_sampling.demo.runner import (
    SCENARIOS,
    latest_comparison,
    run_comparison,
    save_comparison,
    scenario_config,
)
from attain_sampling.sim.mapping import AVAILABLE_METHODS, METHODS, MODELS, PLANNING_MODELS

STATIC_ROOT = Path(__file__).with_name("static")
MAX_REQUEST_BYTES = 16384
REQUEST_BODY_TIMEOUT_S = 2.0
SHOWCASE_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
# Card fields served to the dashboard; the file path and hash stay on the server.
SHOWCASE_FIELDS = (
    "id",
    "title",
    "question",
    "look_for",
    "evidence",
    "focus",
    "compare",
    "key_time_s",
    "key_moment",
    "facts",
    "config",
)


class DemoServer(ThreadingHTTPServer):
    """One simulation at a time; no remote bind, arbitrary paths or external assets."""

    daemon_threads = True

    def __init__(self, port: int, output_root: Path, showcase_root: Path | None = None) -> None:
        super().__init__(("127.0.0.1", port), DemoHandler)
        self.output_root = output_root.resolve()
        # Guided showcases are recorded comparisons written by scripts/make_showcases.py.
        self.showcase_root = (showcase_root or output_root.parent / "showcases").resolve()
        self.latest = latest_comparison(self.output_root)
        self.run_lock = threading.Lock()

    def showcases(self) -> list[dict[str, Any]]:
        """Manifest entries; an absent or malformed manifest means no showcases."""
        path = self.showcase_root / "showcases.json"
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))["showcases"]
        except (OSError, ValueError, KeyError, TypeError):
            return []
        if not isinstance(entries, list):
            return []
        return [
            entry
            for entry in entries
            if isinstance(entry, dict) and SHOWCASE_ID.match(str(entry.get("id", "")))
        ]

    def showcase_bytes(self, name: str) -> bytes | None:
        """The pinned comparison of one showcase, or None if absent or altered."""
        entry = next((item for item in self.showcases() if item["id"] == name), None)
        if entry is None or not isinstance(entry.get("comparison"), str):
            return None
        path = (self.showcase_root / entry["comparison"]).resolve()
        if not path.is_relative_to(self.showcase_root) or not path.is_file():
            return None
        data = path.read_bytes()
        return data if hashlib.sha256(data).hexdigest() == entry.get("sha256") else None


class DemoHandler(BaseHTTPRequestHandler):
    server: DemoServer

    def _bytes(self, data: bytes, content_type: str, *, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, value: Any, *, status: int = 200) -> None:
        self._bytes(
            json.dumps(value, allow_nan=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status=status,
        )

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._json(
                {
                    "mode": "independent_exact_gp",
                    "methods": METHODS,
                    "available_methods": AVAILABLE_METHODS,
                    "models": list(MODELS),
                    "method_models": {"dp": list(PLANNING_MODELS), "p": list(PLANNING_MODELS)},
                    "scenarios": list(SCENARIOS),
                    "controllers": ["filter", "qp"],
                    "controller_models": {"filter": list(MODELS), "qp": ["holonomic"]},
                    "gp_backends": ["exact", "sogp"],
                    "default_gp_backend": "exact",
                    "sogp_demo_capacities": [32, 64, 128],
                    "busy": self.server.run_lock.locked(),
                    "latest_available": self.server.latest is not None,
                    "video_available": self._video_path() is not None,
                    "showcases_available": bool(self.server.showcases()),
                }
            )
        elif path == "/api/showcases":
            keys = SHOWCASE_FIELDS
            self._json(
                {"showcases": [{k: e.get(k) for k in keys} for e in self.server.showcases()]}
            )
        elif path.startswith("/api/showcase/"):
            name = path.removeprefix("/api/showcase/")
            data = self.server.showcase_bytes(name) if SHOWCASE_ID.match(name) else None
            if data is None:
                self._json({"error": "Unknown showcase or altered recording."}, status=404)
            else:
                self._bytes(data, "application/json; charset=utf-8")
        elif path == "/api/latest":
            if self.server.latest is None:
                self._json({"error": "No saved comparison yet. Run a mission."}, status=404)
            else:
                self._bytes(self.server.latest.read_bytes(), "application/json; charset=utf-8")
        elif path == "/api/video":
            video = self._video_path()
            if video is None:
                self._json(
                    {"error": "Export a demo video with attain-sampling record."}, status=404
                )
            else:
                self._bytes(video.read_bytes(), "video/mp4")
        elif path in {"/", "/index.html", "/styles.css", "/app.js"}:
            asset = STATIC_ROOT / ("index.html" if path == "/" else path[1:])
            if not asset.is_file():
                self._json({"error": "Dashboard asset missing"}, status=404)
                return
            kind = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
            self._bytes(asset.read_bytes(), kind + "; charset=utf-8")
        else:
            self._json({"error": "Not found"}, status=404)

    def _video_path(self) -> Path | None:
        if self.server.latest is None:
            return None
        path = self.server.latest.parent / "demo.mp4"
        return path if path.is_file() else None

    def do_POST(self) -> None:
        # Drain an explicitly bounded body before an early 403/404/409 response.
        # Otherwise closing a socket with unread bytes can reset it on Windows,
        # losing a valid JSON rejection. Never hold the simulation lock while
        # waiting for a client to finish sending, and never accept chunked bodies.
        try:
            request_body = self._read_request_body()
        except (ValueError, TimeoutError) as exc:
            self._json({"error": str(exc)}, status=408 if isinstance(exc, TimeoutError) else 400)
            return
        if urlparse(self.path).path != "/api/run":
            self._json({"error": "Not found"}, status=404)
            return
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            self._json({"error": "Cross-origin requests are not accepted"}, status=403)
            return
        if not self.server.run_lock.acquire(blocking=False):
            self._json({"error": "A comparison is running; wait for it to complete."}, status=409)
            return
        response: dict[str, Any]
        response_status = 200
        try:
            body = json.loads(request_body)
            if not isinstance(body, dict):
                raise ValueError("request must be a JSON object")
            allowed = {
                "scenario",
                "robots",
                "seed",
                "duration_s",
                "model",
                "controller",
                "qp_alpha",
                "qp_polygon_sides",
                "qp_max_iter",
                "qp_acceptance_tol",
                "methods",
                "dp_horizon_steps",
                "dp_grid_shape",
                "dp_travel_weight",
                "gp_backend",
                "sogp_max_basis",
                "sogp_novelty_tolerance",
                "target_mean_variance",
            }
            if set(body) - allowed:
                raise ValueError("unknown request fields")
            for name in (
                "robots",
                "seed",
                "qp_polygon_sides",
                "qp_max_iter",
                "dp_horizon_steps",
                "sogp_max_basis",
            ):
                if name in body and (
                    isinstance(body[name], bool) or not isinstance(body[name], int)
                ):
                    raise ValueError(f"{name} must be an integer")
            for name in (
                "qp_alpha",
                "qp_acceptance_tol",
                "dp_travel_weight",
                "sogp_novelty_tolerance",
                "target_mean_variance",
            ):
                if name in body and (
                    isinstance(body[name], bool) or not isinstance(body[name], (int, float))
                ):
                    raise ValueError(f"{name} must be numeric")
            duration = body.get("duration_s", 90.0)
            if isinstance(duration, bool) or not isinstance(duration, (int, float)):
                raise ValueError("duration_s must be numeric")
            if not 10 <= duration <= 300:
                raise ValueError("interactive missions support 10–300 simulated seconds")
            methods = body.pop("methods", list(METHODS))
            if not isinstance(methods, list):
                raise ValueError("methods must be a JSON array")
            if "dp_grid_shape" in body:
                if not isinstance(body["dp_grid_shape"], list):
                    raise ValueError("dp_grid_shape must be a JSON array")
                body["dp_grid_shape"] = tuple(body["dp_grid_shape"])
            config = scenario_config(**body)
            result = run_comparison(
                config, scenario=body.get("scenario", "combined"), methods=tuple(methods)
            )
            destination = save_comparison(result, self.server.output_root)
            self.server.latest = destination / "comparison.json"
            response = result
        except (ValueError, TypeError) as exc:
            response = {"error": str(exc)}
            response_status = 400
        except Exception as exc:
            self.log_error("simulation failed: %s", exc)
            response = {"error": f"Simulation failed: {exc}"}
            response_status = 500
        finally:
            self.server.run_lock.release()
        # Receipt of a completed response must imply the simulation lock is released.
        self._json(response, status=response_status)

    def _read_request_body(self) -> bytes:
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") is not None or len(lengths) != 1:
            raise ValueError("request requires one Content-Length and no Transfer-Encoding")
        try:
            length = int(lengths[0])
        except ValueError as exc:
            raise ValueError("Content-Length must be an integer") from exc
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise ValueError("request must contain 1–16384 bytes of JSON")
        previous_timeout = self.connection.gettimeout()
        deadline = time.monotonic() + REQUEST_BODY_TIMEOUT_S
        chunks: list[bytes] = []
        remaining = length
        try:
            while remaining:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    raise TimeoutError("request body deadline exceeded")
                self.connection.settimeout(timeout)
                chunk = self.rfile.read1(remaining)
                if not chunk:
                    raise ValueError("request body is shorter than Content-Length")
                chunks.append(chunk)
                remaining -= len(chunk)
        finally:
            self.connection.settimeout(previous_timeout)
        return b"".join(chunks)


def serve(port: int = 8765, output_root: Path = Path("outputs/mapping")) -> None:
    with DemoServer(port, output_root) as server:
        print(f"GP Mapping Lab: http://127.0.0.1:{server.server_port}", flush=True)
        print(
            "Independent exact / sparse-online GP simulator. Ctrl+C stops the local server.",
            flush=True,
        )
        count = len(server.showcases())
        print(
            f"Guided showcases: {count} recorded."
            if count
            else "Guided showcases: none yet; run python scripts/make_showcases.py (about 5 min).",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Server stopped.", flush=True)
