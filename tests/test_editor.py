"""The editor uses a real ephemeral loopback server, including in browser tests."""

import json
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import wave
from contextlib import contextmanager
from pathlib import Path

import pytest

from ksmauto.draft import compile_draft
from ksmauto.editor import create_server
from ksmauto.kson import load_kson, save_kson

GRAM = Path(__file__).parent / "fixtures" / "libkson" / "Gram_ex.ksh"
ROOT = Path(__file__).resolve().parents[1]
_NO_BODY = object()


def small_chart():
    chart, errors = compile_draft("title: Test\nbpm: 120\n@m0\n0 A\n1 B~1\n2 l 0 +1:1\n")
    assert not errors
    return chart


@contextmanager
def session(path, **kwargs):
    try:
        server = create_server(path, port=0, **kwargs)
    except PermissionError:
        pytest.skip("this environment forbids loopback sockets")
    with server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)


def request(url, route, method="GET", body=_NO_BODY, headers=None):
    data = json.dumps(body).encode() if body is not _NO_BODY else None
    req = urllib.request.Request(url + route, data=data, method=method, headers=headers or {})
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        result = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
        return response.status, response.headers, result


@pytest.fixture
def chart_path(tmp_path):
    path = tmp_path / "chart.kson"
    save_kson(small_chart(), path)
    return path


def test_chart_save_and_backup(chart_path):
    original = chart_path.read_bytes()
    with session(chart_path) as url:
        code, _, chart = request(url, "/api/chart")
        assert code == 200 and chart == small_chart()
        chart["meta"]["title"] = "Edited"
        chart["extra"] = "preserved with warning"
        code, _, result = request(url, "/api/chart", "PUT", chart)
        assert code == 200 and result["saved"] == str(chart_path)
        assert result["warnings"][0]["level"] == "warning"
        assert load_kson(chart_path) == chart
        backup = chart_path.with_name("chart.kson.bak")
        assert backup.read_bytes() == original
        chart["meta"]["title"] = "Again"
        assert request(url, "/api/chart", "PUT", chart)[0] == 200
        assert backup.read_bytes() == original
        assert request(url, "/api/chart")[2] == chart
        assert not chart_path.with_name("chart.kson.tmp").exists()


@pytest.mark.parametrize("invalid", [None, [], {"format_version": 1}, {"meta": None}])
def test_invalid_chart_rejected(chart_path, invalid):
    before = chart_path.read_bytes()
    with session(chart_path) as url:
        code, _, result = request(url, "/api/chart", "PUT", invalid)
        assert code == 400 and result["issues"]
        assert chart_path.read_bytes() == before
        assert not chart_path.with_name("chart.kson.bak").exists()


def test_overlap_rejected_and_origin_guard(chart_path):
    chart = small_chart()
    chart["note"]["bt"][0] = [[0, 240], 120]
    with session(chart_path) as url:
        assert request(url, "/api/chart", "PUT", chart)[0] == 400
        code, _, _ = request(url, "/api/chart", "PUT", small_chart(), {"Origin": "https://example.org"})
        assert code == 403
        assert request(url, "/api/chart", "PUT", small_chart(), {"Origin": url})[0] == 200


@pytest.mark.parametrize("suffix", [".ksh", ".ksmd"])
def test_import_save_target(tmp_path, suffix):
    source = tmp_path / ("import" + suffix)
    text = "title=Test\nt=120\n--\n1000|00|--\n--\n" if suffix == ".ksh" else "title: Test\nbpm: 120\n@m0\n0 A\n"
    source.write_text(text)
    with session(source) as url:
        _, _, chart = request(url, "/api/chart")
        assert request(url, "/api/chart", "PUT", chart)[2]["saved"] == str(source.with_suffix(".kson"))
        assert load_kson(source.with_suffix(".kson")) == chart
        assert source.read_text() == text


def silent_wav(path, seconds=4):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * 8000 * seconds)


def test_audio_and_ranges(chart_path, tmp_path):
    audio = tmp_path / "silent.wav"
    silent_wav(audio)
    content = audio.read_bytes()
    chart = load_kson(chart_path)
    chart.setdefault("audio", {}).setdefault("bgm", {})["filename"] = audio.name
    save_kson(chart, chart_path)
    with session(chart_path) as url:
        code, headers, data = request(url, "/api/audio")
        assert code == 200 and data == content
        assert headers.get_content_type() in {"audio/wav", "audio/x-wav", "audio/vnd.wave"}
        for requested, start, end in [("bytes=4-19", 4, 19), ("bytes=44-", 44, len(content) - 1),
                                      ("bytes=-12", len(content) - 12, len(content) - 1),
                                      ("bytes=0-999999", 0, len(content) - 1)]:
            code, headers, data = request(url, "/api/audio", headers={"Range": requested})
            assert code == 206 and data == content[start:end + 1]
            assert headers["Content-Range"] == f"bytes {start}-{end}/{len(content)}"
            assert int(headers["Content-Length"]) == len(data)
            assert headers["Accept-Ranges"] == "bytes"
        for requested in ["bytes=999999-", "bytes=9-2", "bytes=-0", "bytes=-", "nonsense", "bytes=0-2,4-6"]:
            code, headers, _ = request(url, "/api/audio", headers={"Range": requested})
            assert code == 416 and headers["Content-Range"] == f"bytes */{len(content)}"


def test_api_tools(chart_path, tmp_path):
    analysis = {"audio": {"duration_sec": 0.1}, "tempo": {"time_sig": [4, 4]},
                "measures": [{"index": 0, "start_sec": 0, "energy": 1, "onsets": {"all": [[0, 1]]}}]}
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis))
    with session(chart_path, analysis=path) as url:
        assert request(url, "/api/analysis")[2] == analysis
        code, _, result = request(url, "/api/lint", "POST", small_chart())
        assert code == 200 and result["stats"]["bt_chips"] == 1
        assert any(f["rule"] == "after-audio" for f in result["findings"])
        code, _, result = request(url, "/api/decompile", "POST", small_chart())
        assert code == 200 and 'title: "Test"' in result["text"] and "warnings" in result
        code, _, compiled = request(url, "/api/compile", "POST", {"text": result["text"], "base": small_chart()})
        assert code == 200 and not compiled["errors"]
        assert compiled["chart"]["note"] == small_chart()["note"]
        code, _, result = request(url, "/api/compile", "POST", {"text": "bad header", "base": small_chart()})
        assert code == 200 and result["errors"][0]["line"] == 1 and result["errors"][0]["col"] == 1
        assert request(url, "/api/compile", "POST", {"text": 1, "base": small_chart()})[0] == 400
        assert request(url, "/api/lint", "POST", {})[0] == 400


def test_static_paths_and_missing_optional_files(chart_path):
    with session(chart_path) as url:
        code, headers, html = request(url, "/")
        assert code == 200 and b'<canvas id="highway"' in html
        assert headers.get_content_type() == "text/html"
        assert request(url, "/timing.js")[1].get_content_type() == "text/javascript"
        assert request(url, "/style.css")[0] == 200
        for route in ["/../kson.py", "/%2e%2e/kson.py", "/%2e%2e%2fkson.py", "/server.py"]:
            assert request(url, route)[0] == 403
        for route in ["/api/audio", "/api/analysis", "/missing.js"]:
            assert request(url, route)[0] == 404


def test_cli_editor_options(chart_path, monkeypatch):
    from ksmauto.cli import main
    import ksmauto.editor

    calls = []
    monkeypatch.setattr(ksmauto.editor, "run", lambda *args, **kw: calls.append((args, kw)) or 0)
    assert main(["edit", str(chart_path), "--audio", "song.wav", "--analysis", "analysis.json",
                 "--port", "1234", "--no-browser"]) == 0
    assert calls == [((chart_path,), {"audio": Path("song.wav"), "analysis": Path("analysis.json"),
                                      "port": 1234, "no_browser": True})]


def node_executable():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    return node


def test_editor_js():
    node = node_executable()
    help_text = subprocess.run([node, "--help"], capture_output=True, text=True, timeout=10).stdout
    flags = ["--experimental-test-isolation=none"] if "--experimental-test-isolation" in help_text else []
    result = subprocess.run([node, "--test", *flags, "tests/editor.test.mjs"], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_editor_browser(tmp_path):
    node = node_executable()
    available = subprocess.run([node, "-e", "require('playwright')"], cwd=ROOT, capture_output=True)
    if available.returncode:
        pytest.skip("node playwright is not installed")
    audio = tmp_path / "silent.wav"
    silent_wav(audio)
    # Use a copy so interactive smoke checks can save without touching fixtures.
    source = tmp_path / GRAM.name
    shutil.copyfile(GRAM, source)
    with session(source, audio=audio) as url:
        result = subprocess.run([node, "tests/editor-smoke.cjs", url], cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
    if result.returncode == 77:
        pytest.skip("playwright Chromium is not installed")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def direct_session(monkeypatch):
    """Exercise the actual HTTP handler in memory even when sockets are forbidden."""
    import http.client
    import io
    from types import SimpleNamespace
    import ksmauto.editor.server as module

    class Connection:
        def __init__(self, data):
            self.data = data
            self.output = []

        def makefile(self, *args):
            return io.BytesIO(self.data)

        def sendall(self, data):
            self.output.append(bytes(data))

    monkeypatch.setattr(module, "ThreadingHTTPServer", lambda address, handler:
                        SimpleNamespace(server_port=address[1], handler=handler))

    def start(path, **kwargs):
        server = create_server(path, port=0, **kwargs)

        def dispatch(route, method="GET", body=_NO_BODY, headers=None):
            payload = b"" if body is _NO_BODY else json.dumps(body).encode()
            lines = [f"{method} {route} HTTP/1.0", "Host: 127.0.0.1", f"Content-Length: {len(payload)}"]
            lines.extend(f"{k}: {v}" for k, v in (headers or {}).items())
            connection = Connection(("\r\n".join(lines) + "\r\n\r\n").encode() + payload)
            server.handler(connection, ("127.0.0.1", 12345), server)
            response = http.client.HTTPResponse(Connection(b"".join(connection.output)))
            response.begin()
            raw = response.read()
            data = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
            return response.status, response.headers, data

        return dispatch

    return start


@pytest.mark.parametrize("imported", [False, True])
def test_direct_save_validation_backup(direct_session, chart_path, imported, tmp_path):
    if imported:
        source = tmp_path / "import.ksh"
        source.write_text("title=Test\nt=120\n--\n1000|00|--\n--\n")
        target = source.with_suffix(".kson")
        save_kson(small_chart(), target)
    else:
        source = target = chart_path
    original = target.read_bytes()
    call = direct_session(source)
    code, _, chart = call("/api/chart")
    assert code == 200
    chart["meta"]["title"] = "Saved from HTTP handler"
    code, _, result = call("/api/chart", "PUT", chart)
    assert code == 200 and result["saved"] == str(target)
    assert load_kson(target) == chart
    assert call("/api/chart")[2] == chart
    for invalid in [None, [], {}, {"meta": None}]:
        assert call("/api/chart", "PUT", invalid)[0] == 400
    chart["meta"]["title"] = "Second save"
    assert call("/api/chart", "PUT", chart)[0] == 200
    assert target.with_name(target.name + ".bak").read_bytes() == original
    if imported:
        assert "title=Test" in source.read_text()


def test_direct_audio_static(direct_session, chart_path, tmp_path):
    audio = tmp_path / "test.wav"
    silent_wav(audio)
    call = direct_session(chart_path, audio=audio)
    assert call("/")[0] == 200
    assert call("/app.js")[1].get_content_type() == "text/javascript"
    assert call("/%2e%2e/kson.py")[0] == 403
    assert call("/server.py")[0] == 403
    assert call("/missing.js")[0] == 404
    assert call("/api/analysis")[0] == 404
    content = audio.read_bytes()
    assert call("/api/audio")[2] == content
    for requested, start, end in [("bytes=2-8", 2, 8), ("bytes=-5", len(content) - 5, len(content) - 1),
                                  ("bytes=44-", 44, len(content) - 1)]:
        code, headers, data = call("/api/audio", headers={"Range": requested})
        assert code == 206 and data == content[start:end + 1]
        assert headers["Content-Range"] == f"bytes {start}-{end}/{len(content)}"
    for requested in ["bytes=999999-", "bytes=9-2", "bytes=-0", "bytes=-", "nonsense", "bytes=0-2,4-6"]:
        assert call("/api/audio", headers={"Range": requested})[0] == 416


def test_direct_tools(direct_session, chart_path, tmp_path):
    analysis = {"audio": {"duration_sec": 0.1}, "tempo": {"time_sig": [4, 4]},
                "measures": [{"index": 0, "energy": 1, "onsets": {"all": [[0, 1]]}}]}
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(analysis))
    call = direct_session(chart_path, analysis=analysis_path)
    assert call("/api/analysis")[2] == analysis
    code, _, result = call("/api/lint", "POST", small_chart())
    assert code == 200 and result["stats"]["bt_chips"] == 1
    assert any(f["rule"] == "after-audio" for f in result["findings"])
    code, _, draft = call("/api/decompile", "POST", small_chart())
    assert code == 200 and 'title: "Test"' in draft["text"]
    code, _, compiled = call("/api/compile", "POST", {"text": draft["text"], "base": small_chart()})
    assert code == 200 and not compiled["errors"] and compiled["chart"]["note"] == small_chart()["note"]
    code, _, bad = call("/api/compile", "POST", {"text": "bad header", "base": small_chart()})
    assert code == 200 and bad["errors"][0]["line"] == 1
    assert call("/api/chart", "PUT", small_chart(), {"Origin": "https://example.org"})[0] == 403
