"""The demo proxy injects exactly the configured faults and forwards everything else."""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from demo.fault_proxy import SCENARIOS, Fault, start


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        body = json.dumps({"contact": {"email": "a@b.c", "name": "B&B"}, "path": self.path})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", "token=abc; Domain=sandbox.example; Secure; HttpOnly")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture
def proxy(monkeypatch):
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    monkeypatch.setitem(
        SCENARIOS,
        "test",
        [
            Fault("down", "GET", r"^/api/report", "status", 503),
            Fault("contract", "GET", r"^/api/branding$", "drop", "contact.email"),
            Fault("text", "GET", r"^/api/booking$", "replace", ("B&B", "Hotel")),
        ],
    )
    server = start("test", upstream=f"http://127.0.0.1:{upstream.server_address[1]}")
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    upstream.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response, json.loads(response.read())


def test_unmatched_requests_are_forwarded_unchanged(proxy):
    response, body = get(f"{proxy}/api/room?x=1")
    assert body["path"] == "/api/room?x=1"
    assert body["contact"]["email"] == "a@b.c"
    assert response.headers.get("X-Demo-Fault") is None
    cookie = response.headers["Set-Cookie"]
    assert "Secure" not in cookie and "Domain" not in cookie and "HttpOnly" in cookie


def test_status_fault_answers_without_calling_upstream(proxy):
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(f"{proxy}/api/report/1", timeout=10)
    assert error.value.code == 503
    assert error.value.headers["X-Demo-Fault"] == "down"


def test_body_faults_change_only_the_targeted_content(proxy):
    _, branding = get(f"{proxy}/api/branding")
    _, booking = get(f"{proxy}/api/booking")
    assert "email" not in branding["contact"]
    assert booking["contact"] == {"email": "a@b.c", "name": "Hotel"}


def test_release_regression_scenario_mixes_three_kinds_of_cause():
    kinds = {fault.kind for fault in SCENARIOS["release-regression"]}
    assert kinds == {"replace", "status", "drop"}
