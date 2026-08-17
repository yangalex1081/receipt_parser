"""All tests for the receipt-parser backend, offline and live.

    pytest backend/tests/ -v                              # offline only (fast)
    RUN_LIVE=1 pytest backend/tests/ -v                   # + hit the deployment
    RUN_LIVE=1 RUN_LIVE_PARSE=1 pytest backend/tests/ -v  # + a real GPU parse

Two kinds of test live here:

  OFFLINE — Modal is stubbed, nothing touches the network. These test the code:
    auth logic, upload validation, result states, response shape. They run
    anywhere, including CI, and never cost anything.

  LIVE — hits the real Netlify site and Modal app. These test the deployment,
    not the code: that Netlify is signing, that Modal verifies the signature,
    that netlify.toml points at the right URL. Skipped unless RUN_LIVE is set.

If offline passes but live fails, the code is fine and the deploy is
misconfigured. That distinction is the whole reason both exist.
"""

import os
import re
import sys
import time
from pathlib import Path

import pytest

# --------------------------------------------------------------------------
# Setup — must run before `gateway` is imported, which reads the secret at
# module scope.
# --------------------------------------------------------------------------

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

TEST_SECRET = "t" * 40
os.environ.setdefault("NETLIFY_SIGN_SECRET", TEST_SECRET)

import httpx  # noqa: E402
import jwt  # noqa: E402
import modal  # noqa: E402

SITE = os.environ.get("SITE_URL", "https://alexs-receipt-parser.netlify.app")
MODAL = os.environ.get(
    "MODAL_URL", "https://yangalex1081--receipt-parser-fastapi-app.modal.run"
)

# Cold start was measured at ~66s.
TIMEOUT = httpx.Timeout(120.0)

# Applied per-test so live tests can share this file with offline ones.
live = pytest.mark.skipif(
    not os.environ.get("RUN_LIVE"), reason="live tests are opt-in; set RUN_LIVE=1"
)

SIGNED_ROUTES = [
    ("get", "/status"),
    ("get", "/result/fc-TEST123"),
    ("post", "/parse"),
]


# --------------------------------------------------------------------------
# Modal stubs
# --------------------------------------------------------------------------

class FakeCall:
    """Stands in for the object returned by Function.spawn()."""
    object_id = "fc-TEST123"


class FakeProcessReceipt:
    def __init__(self):
        self.spawn_calls = []

    def spawn(self, *args, **kwargs):
        self.spawn_calls.append((args, kwargs))
        return FakeCall()


class FakeGetStatus:
    def remote(self, *args, **kwargs):
        return {"status": "ready", "gpu": False, "device": "cpu", "model": "donut"}


class FakeFunctionCall:
    """Drives /result through its four outcomes via `mode`."""

    mode = "pending"

    def __init__(self, call_id):
        self.call_id = call_id

    @classmethod
    def from_id(cls, call_id):
        return cls(call_id)

    def get(self, timeout=0):
        if FakeFunctionCall.mode == "pending":
            raise TimeoutError()
        if FakeFunctionCall.mode == "expired":
            raise modal.exception.OutputExpiredError()
        if FakeFunctionCall.mode == "failed":
            raise RuntimeError("gpu exploded")
        # price is the LINE TOTAL, so total == sum(price), never sum(price*qty).
        return {
            "store": "Test Mart",
            "date": "2026-08-14",
            "total": 15.00,
            "items": [
                {"name": "Apples", "qty": 3, "price": 9.00},
                {"name": "Latte", "qty": 2, "price": 6.00},
            ],
        }


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def gw(monkeypatch):
    """The gateway module with Modal stubbed out."""
    import gateway

    monkeypatch.setattr(gateway, "process_receipt", FakeProcessReceipt())
    monkeypatch.setattr(gateway, "get_status", FakeGetStatus())
    monkeypatch.setattr(gateway.modal, "FunctionCall", FakeFunctionCall)
    monkeypatch.setattr(gateway, "NETLIFY_SIGN_SECRET", TEST_SECRET)
    FakeFunctionCall.mode = "pending"
    return gateway


@pytest.fixture
def client(gw):
    from fastapi.testclient import TestClient

    return TestClient(gw.web_app)


@pytest.fixture
def sign():
    """Build an x-nf-sign header the way Netlify would."""

    def _sign(secret=TEST_SECRET, **overrides):
        claims = {
            "iss": "netlify",
            "site_url": "https://alexs-receipt-parser.netlify.app",
            "deploy_context": "production",
            "netlify_id": "1be0f471-6532-45ff-b1b1-f9c66ea24dc1",
            "exp": int(time.time()) + 300,
        }
        claims.update(overrides)
        return {"x-nf-sign": jwt.encode(claims, secret, algorithm="HS256")}

    return _sign


@pytest.fixture
def image_file():
    """A minimal JPEG-ish upload."""
    return {"file": ("receipt.jpg", b"\xff\xd8\xff" + b"x" * 1024, "image/jpeg")}


# ==========================================================================
# OFFLINE — GET /health (public)
# ==========================================================================

def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_ignores_a_bad_signature(client):
    """Health is an uptime probe; it must not care about auth either way."""
    r = client.get("/health", headers={"x-nf-sign": "garbage"})
    assert r.status_code == 200


# ==========================================================================
# OFFLINE — signature enforcement, applied to every protected route
# ==========================================================================

@pytest.mark.parametrize("method,path", SIGNED_ROUTES)
def test_rejects_missing_signature(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 401
    assert "x-nf-sign" in r.json()["detail"]


@pytest.mark.parametrize("method,path", SIGNED_ROUTES)
def test_rejects_malformed_signature(client, method, path):
    r = getattr(client, method)(path, headers={"x-nf-sign": "not.a.jwt"})
    assert r.status_code == 401


@pytest.mark.parametrize("method,path", SIGNED_ROUTES)
def test_rejects_wrong_secret(client, sign, method, path):
    r = getattr(client, method)(path, headers=sign(secret="wrong-secret-value-here-32b"))
    assert r.status_code == 401


@pytest.mark.parametrize("method,path", SIGNED_ROUTES)
def test_rejects_expired_signature(client, sign, method, path):
    r = getattr(client, method)(path, headers=sign(exp=int(time.time()) - 10))
    assert r.status_code == 401
    assert r.json()["detail"] == "Signature expired"


@pytest.mark.parametrize("method,path", SIGNED_ROUTES)
def test_rejects_wrong_issuer(client, sign, method, path):
    r = getattr(client, method)(path, headers=sign(iss="attacker"))
    assert r.status_code == 401
    assert r.json()["detail"] == "Unexpected issuer"


@pytest.mark.parametrize("method,path", SIGNED_ROUTES)
def test_rejects_alg_none_forgery(client, method, path):
    """Algorithms are pinned to HS256, so an unsigned token must not pass."""
    token = jwt.encode({"iss": "netlify", "exp": int(time.time()) + 300}, None, algorithm="none")
    r = getattr(client, method)(path, headers={"x-nf-sign": token})
    assert r.status_code == 401


def test_500_when_server_secret_is_missing(client, gw, monkeypatch, sign):
    """A misconfigured deploy should say so, not silently accept traffic.

    This is exactly the failure the live deployment hit when the Modal secret
    held the wrong key name.
    """
    monkeypatch.setattr(gw, "NETLIFY_SIGN_SECRET", None)
    r = client.get("/status", headers=sign())
    assert r.status_code == 500
    assert "NETLIFY_SIGN_SECRET" in r.json()["detail"]


# ==========================================================================
# OFFLINE — POST /parse
# ==========================================================================

def test_parse_returns_call_id(client, sign, image_file):
    r = client.post("/parse", files=image_file, headers=sign())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["call_id"] == "fc-TEST123"


def test_parse_forwards_image_bytes(client, gw, sign, image_file):
    client.post("/parse", files=image_file, headers=sign())
    (args, _kwargs) = gw.process_receipt.spawn_calls[0]
    assert args[0].startswith(b"\xff\xd8\xff")


def test_parse_rejects_non_image(client, sign):
    r = client.post(
        "/parse", files={"file": ("notes.txt", b"hello", "text/plain")}, headers=sign()
    )
    assert r.status_code == 400


def test_parse_rejects_empty_file(client, sign):
    r = client.post(
        "/parse", files={"file": ("empty.jpg", b"", "image/jpeg")}, headers=sign()
    )
    assert r.status_code == 400


def test_parse_rejects_oversize_upload(client, sign):
    """Netlify caps bodies ~4.5MB binary; the gateway enforces 6MB itself."""
    big = {"file": ("big.jpg", b"x" * (7 * 1024 * 1024), "image/jpeg")}
    r = client.post("/parse", files=big, headers=sign())
    assert r.status_code == 413


# ==========================================================================
# OFFLINE — GET /result/{call_id}
# ==========================================================================

def test_result_pending(client, sign):
    FakeFunctionCall.mode = "pending"
    r = client.get("/result/fc-TEST123", headers=sign())
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_result_done_returns_payload(client, sign):
    FakeFunctionCall.mode = "done"
    r = client.get("/result/fc-TEST123", headers=sign())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["result"]["store"] == "Test Mart"
    assert body["result"]["items"][0]["qty"] == 3


def test_price_is_a_line_total_not_a_unit_price(client, sign):
    """Pins the schema both sides depend on.

    CORD's `price` is the total for the row, so the receipt total is
    sum(price). If anything starts multiplying by qty, this fails: the
    qty-weighted sum here would be 39.00, not 15.00.
    """
    FakeFunctionCall.mode = "done"
    result = client.get("/result/fc-TEST123", headers=sign()).json()["result"]

    line_sum = sum(i["price"] for i in result["items"])
    qty_weighted = sum(i["price"] * i["qty"] for i in result["items"])

    assert result["total"] == pytest.approx(line_sum)
    assert result["total"] != pytest.approx(qty_weighted)


def test_result_expired(client, sign):
    FakeFunctionCall.mode = "expired"
    r = client.get("/result/fc-TEST123", headers=sign())
    assert r.status_code == 410


def test_result_job_failure(client, sign):
    """A crashed GPU job must surface, not poll forever."""
    FakeFunctionCall.mode = "failed"
    r = client.get("/result/fc-TEST123", headers=sign())
    assert r.status_code == 500


# ==========================================================================
# OFFLINE — GET /status and the response contract
# ==========================================================================

def test_status_returns_device_info(client, sign):
    r = client.get("/status", headers=sign())
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_result_shape_matches_frontend_expectations(client, sign):
    """ReceiptTable reads result.items[].{name,qty,price}; keep them in sync."""
    FakeFunctionCall.mode = "done"
    result = client.get("/result/fc-TEST123", headers=sign()).json()["result"]
    assert set(result) >= {"store", "date", "total", "items"}
    assert set(result["items"][0]) >= {"name", "qty", "price"}


# ==========================================================================
# LIVE — requires RUN_LIVE=1
# ==========================================================================

@live
def test_live_site_serves():
    r = httpx.get(SITE, timeout=TIMEOUT, follow_redirects=True)
    assert r.status_code == 200


@live
def test_live_bundle_contains_no_credentials():
    """Regression guard: the whole point of the signed-proxy work."""
    page = httpx.get(SITE, timeout=TIMEOUT, follow_redirects=True).text
    m = re.search(r'src="(/assets/index-[^"]+\.js)"', page)
    assert m, "could not find the JS bundle"

    js = httpx.get(SITE + m.group(1), timeout=TIMEOUT).text
    assert "Bearer" not in js
    assert "modal.run" not in js
    assert "VITE_API_KEY" not in js


@live
def test_live_health_through_proxy():
    """Proves netlify.toml routes to a live Modal app."""
    r = httpx.get(f"{SITE}/api/health", timeout=TIMEOUT)
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
    assert r.json()["status"] == "ok"


@live
def test_live_modal_rejects_unsigned_requests():
    """The core security property: Modal is not directly usable.

    A 500 here means the Modal secret is missing NETLIFY_SIGN_SECRET.
    """
    r = httpx.post(f"{MODAL}/parse", timeout=TIMEOUT)
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"


@live
def test_live_modal_rejects_forged_signature():
    r = httpx.get(
        f"{MODAL}/status", headers={"x-nf-sign": "forged.token.here"}, timeout=TIMEOUT
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"


@live
def test_live_modal_health_is_public():
    """/health is deliberately unauthenticated so uptime probes work."""
    r = httpx.get(f"{MODAL}/health", timeout=TIMEOUT)
    assert r.status_code == 200


@live
def test_live_result_endpoint_is_signed_by_netlify():
    r = httpx.get(f"{SITE}/api/result/fc-does-not-exist", timeout=TIMEOUT)
    # Netlify signs it, so it reaches Modal and fails on the unknown id.
    # Anything but 401 means the signature made it through.
    assert r.status_code != 401


@live
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_PARSE"),
    reason="costs a GPU invocation; set RUN_LIVE_PARSE=1",
)
def test_live_full_parse_round_trip():
    """Upload -> poll -> result, the way the browser does it."""
    photo = BACKEND.parent / "test_photos" / "sample21.jpg"
    if not photo.exists():
        pytest.skip("no sample receipt available")

    r = httpx.post(
        f"{SITE}/api/parse",
        files={"file": ("sample21.jpg", photo.read_bytes(), "image/jpeg")},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    call_id = r.json()["call_id"]

    deadline = time.time() + 150
    while time.time() < deadline:
        time.sleep(3)
        poll = httpx.get(f"{SITE}/api/result/{call_id}", timeout=TIMEOUT)
        assert poll.status_code == 200, f"{poll.status_code}: {poll.text[:200]}"
        body = poll.json()
        if body["status"] == "done":
            assert "items" in body["result"]
            return

    pytest.fail("parse did not finish within 150s")
