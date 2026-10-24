"""Loopback-only HTTP API for one chart and its audio."""

import json
import mimetypes
import re
import shutil
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ..draft import compile_draft, decompile
from ..kson import dumps_kson, validate
from ..lint import lint, stats
from ..timing import TimingMap

STATIC = Path(__file__).parent.resolve()


def _issues(chart):
    issues = [asdict(i) for i in validate(chart)]
    if not any(i["level"] == "error" for i in issues):
        try:
            TimingMap(chart["beat"])
        except ValueError as exc:
            issues.append({"level": "error", "path": "$.beat", "message": str(exc)})
    return issues


def create_server(path, *, audio=None, analysis=None, port=8765):
    """Load a session; callers own serve_forever(), shutdown(), and server_close()."""
    from ..cli import _load

    path = Path(path).resolve()
    if path.suffix.lower() not in {".kson", ".ksh", ".ksmd"}:
        raise ValueError("Expected a .kson, .ksh, or .ksmd chart")
    chart = _load(path)
    errors = [i for i in _issues(chart) if i["level"] == "error"]
    if errors:
        raise ValueError(str(errors))
    target = path if path.suffix.lower() == ".kson" else path.with_suffix(".kson")
    filename = chart.get("audio", {}).get("bgm", {}).get("filename")
    audio_path = Path(audio).resolve() if audio else (path.parent / filename if filename else None)
    analysis_data = json.loads(Path(analysis).read_text(encoding="utf-8")) if analysis else None
    lock = threading.Lock()
    backed_up = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def json_response(self, value, status=200, headers=None):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32 * 1024 * 1024:
                raise ValueError("Expected a JSON body of at most 32 MiB")
            def invalid_number(value):
                raise ValueError(f"Invalid JSON number: {value}")

            return json.loads(self.rfile.read(size), parse_constant=invalid_number)

        def file_response(self, path, *, ranges=False):
            try:
                stream = path.open("rb")
            except (FileNotFoundError, IsADirectoryError):
                self.json_response({"error": "File not found"}, 404)
                return
            with stream:
                size = path.stat().st_size
                start, end, status = 0, size - 1, 200
                requested = self.headers.get("Range") if ranges else None
                if requested:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                    if match and any(match.groups()) and size:
                        a, b = match.groups()
                        if a:
                            start = int(a)
                            end = min(int(b), size - 1) if b else size - 1
                        else:
                            start = max(0, size - int(b))
                        status = 206
                    if (not match or not any(match.groups()) or start > end
                            or start >= size or not size):
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                length = end - start + 1
                self.send_response(status)
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                # .js must be a JavaScript MIME type for browser ES modules.
                if path.suffix == ".js":
                    mime = "text/javascript"
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(length))
                self.send_header("Cache-Control", "no-store")
                if ranges:
                    self.send_header("Accept-Ranges", "bytes")
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                stream.seek(start)
                while length > 0:
                    data = stream.read(min(length, 65536))
                    if not data:
                        break
                    self.wfile.write(data)
                    length -= len(data)

        def do_GET(self):
            route = unquote(urlsplit(self.path).path)
            try:
                if route == "/api/chart":
                    with lock:
                        self.json_response(chart, headers={
                            "X-Editor-Audio": str(bool(audio_path and audio_path.is_file())).lower(),
                            "X-Editor-Analysis": str(analysis_data is not None).lower(),
                        })
                elif route == "/api/analysis":
                    self.json_response(analysis_data if analysis_data is not None else {"error": "No analysis"},
                                       200 if analysis_data is not None else 404)
                elif route == "/api/audio":
                    if audio_path is None:
                        self.json_response({"error": "No audio configured"}, 404)
                    else:
                        self.file_response(audio_path, ranges=True)
                else:
                    relative = "index.html" if route == "/" else route.lstrip("/")
                    file = (STATIC / relative).resolve()
                    if ".." in Path(relative).parts or not file.is_relative_to(STATIC) or file.suffix not in {".html", ".css", ".js", ".ico"}:
                        self.json_response({"error": "Forbidden path"}, 403)
                    else:
                        self.file_response(file)
            except (OSError, ValueError) as exc:
                self.json_response({"error": str(exc)}, 400)

        def do_PUT(self):
            self.mutate("PUT")

        def do_POST(self):
            self.mutate("POST")

        def mutate(self, method):
            nonlocal chart, backed_up
            route = urlsplit(self.path).path
            if (method, route) not in {("PUT", "/api/chart"), ("POST", "/api/lint"),
                                       ("POST", "/api/decompile"), ("POST", "/api/compile")}:
                self.json_response({"error": "Unknown endpoint"}, 404)
                return
            # Reject cross-origin browser writes to this local service.
            origin = self.headers.get("Origin")
            expected = f"http://127.0.0.1:{self.server.server_port}"
            if origin and origin != expected:
                self.json_response({"error": "Cross-origin write rejected"}, 403)
                return
            try:
                data = self.body()
                candidate = data.get("base") if route == "/api/compile" and isinstance(data, dict) else data
                issues = _issues(candidate)
                if any(i["level"] == "error" for i in issues):
                    self.json_response({"issues": issues}, 400)
                    return
                if route == "/api/chart":
                    serialized = dumps_kson(data)
                    with lock:
                        if target.exists() and not backed_up:
                            shutil.copyfile(target, target.with_name(target.name + ".bak"))
                            backed_up = True
                        temporary = target.with_name(target.name + ".tmp")
                        try:
                            temporary.write_text(serialized, encoding="utf-8", newline="\n")
                            temporary.replace(target)
                        finally:
                            temporary.unlink(missing_ok=True)
                        chart = data
                    self.json_response({"saved": str(target), "warnings": issues})
                elif route == "/api/lint":
                    self.json_response({"findings": [asdict(f) for f in lint(data, analysis_data)], "stats": stats(data)})
                elif route == "/api/decompile":
                    text, warnings = decompile(data)
                    self.json_response({"text": text, "warnings": warnings})
                else:
                    if not isinstance(data.get("text"), str):
                        raise ValueError("text must be a string")
                    result, errors = compile_draft(data["text"], data["base"])
                    self.json_response({"chart": result, "errors": [asdict(e) for e in errors]})
            except (ValueError, TypeError, KeyError) as exc:
                self.json_response({"error": str(exc)}, 400)
            except OSError as exc:
                self.json_response({"error": str(exc)}, 500)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def run(path, *, audio=None, analysis=None, port=8765, no_browser=False):
    with create_server(path, audio=audio, analysis=analysis, port=port) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(url, flush=True)
        if not no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
