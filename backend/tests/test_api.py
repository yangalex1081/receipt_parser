"""Functionality tests for the receipt-parser backend.

    pytest                  # offline only (fast, free, the default)
    pytest -m live          # the deploy checks instead
    pytest -m "live or not live"   # everything

Every test here answers a yes/no question. How *well* the parser reads a
receipt is not a yes/no question, so it is not tested here at all — that lives
in local_testing/eval/, which scores prompts and models against hand-labelled
receipts and reports numbers rather than asserts. Keep the two apart: an eval
turned into an assert either has a threshold so loose it never fires or so
tight it fails on noise.

Two kinds of test live in this file:

  OFFLINE (default) — Modal is stubbed, nothing touches the network. These test
    the code: auth logic, upload validation, result states, response shape, and
    each of the four GPU-app functions in funcs.py. They run anywhere,
    including CI, and never cost anything.

    The funcs.py functions are exercised through `.local()`, which runs the
    body in-process — the same code Modal runs, minus the container. Three of
    the four run fully offline; transcript_receipt needs the weights, so here
    it is covered by its contract (the prompt and the image constants) and the
    model itself is measured in the eval harness.

  LIVE (`-m live`) — hits the real Netlify site and Modal app. These test the
    deployment, not the code: that Netlify is signing, that Modal verifies the
    signature, that netlify.toml points at the right URL. None of them invoke
    the GPU; scoring the deployed model is `run_eval.py --modal`.

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

# Applied per-test so live tests can share this file with offline ones. pytest.ini
# deselects them by default; `pytest -m live` runs them.
live = pytest.mark.live

SIGNED_ROUTES = [
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


# What the model would reply for the stubbed job. It is a raw string rather
# than a finished payload because the stub below runs it through the real
# normalize_output: a done result must be something funcs.py can actually
# produce, or the gateway tests drift from the deployment while still passing.
#
# price is the LINE TOTAL, so total == sum(price), never sum(price*qty).
STUB_REPLY = """{
  "store": "Test Mart",
  "date": "2026-08-14",
  "total": 15.00,
  "items": [
    {"name": "APPLES", "qty": 3, "price": 9.00},
    {"name": "LATTE", "qty": 2, "price": 6.00}
  ]
}"""


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

        import funcs

        return funcs.normalize_output.local(STUB_REPLY)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def gw(monkeypatch):
    """The gateway module with Modal stubbed out."""
    import gateway

    monkeypatch.setattr(gateway, "process_receipt", FakeProcessReceipt())
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
    r = client.get("/result/fc-TEST123", headers=sign())
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
    """Pins the schema both sides depend on, end to end.

    `price` is the total for the row, so the receipt total is sum(price). The
    numbers here come out of the real normalize_output, so if that ever starts
    multiplying by qty this fails: the qty-weighted sum would be 39.00, not
    15.00.
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
# OFFLINE — response contract
# ==========================================================================

def test_result_shape_matches_frontend_expectations(client, sign):
    """ReceiptTable reads result.printed_total and result.items[].{name,qty,price};
    keep them in sync.

    The payload is real normalize_output run through the gateway and out as
    JSON, so this covers the whole handoff — including that every value
    survives serialization."""
    FakeFunctionCall.mode = "done"
    result = client.get("/result/fc-TEST123", headers=sign()).json()["result"]
    assert set(result) >= {"store", "date", "total", "printed_total", "items"}
    assert set(result["items"][0]) >= {"name", "qty", "price"}


# ==========================================================================
# LIVE — deployment checks; run with `pytest -m live`
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
        f"{MODAL}/result/fc-nope", headers={"x-nf-sign": "forged.token.here"}, timeout=TIMEOUT
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


# The two tests that used to sit here ran the model on a single photo and
# asserted `items != []`. That is an eval with one case and a threshold of
# zero: it passes for a prompt that reads half the rows, and it costs a GPU
# invocation to tell you so. `python local_testing/eval/run_eval.py --modal`
# asks the same question of the same deployment across six labelled receipts
# and answers it with an F1.


# ==========================================================================
# OFFLINE — normalize_output
#
# Pure function, no GPU: feed it the strings Qwen3-VL actually emits and check
# the schema the frontend consumes. This is where extraction regressions
# surface cheapest.
#
# The input is now a *string* rather than Donut's decoded dict, because a
# generative model returns text. Everything below is a plausible reply, not a
# hypothetical one: the fences, the preamble, the hallucinated TOTAL row and
# the currency symbols are all things a VLM does.
# ==========================================================================

@pytest.fixture
def normalize():
    import funcs

    return funcs.normalize_output.local


QWEN_REPLY = """{
  "store": "PARKNSHOP",
  "date": "2026-08-14",
  "total": 88.50,
  "items": [
    {"name": "ICE BLACKCOFFEE", "qty": 2, "price": 50.00},
    {"name": "MUFFIN", "qty": 3, "price": 38.50}
  ]
}"""


def test_normalize_extracts_the_full_schema(normalize):
    """store and date are real fields now — CORD-v2 had nowhere to put them."""
    out = normalize(QWEN_REPLY)
    assert out["store"] == "PARKNSHOP"
    assert out["date"] == "2026-08-14"
    assert [i["name"] for i in out["items"]] == ["Ice Blackcoffee", "Muffin"]
    assert out["items"][0]["qty"] == 2
    assert out["items"][0]["price"] == 50.0


def test_normalize_strips_markdown_fences(normalize):
    """The prompt forbids fences. Models emit them anyway."""
    out = normalize("```json\n" + QWEN_REPLY + "\n```")
    assert out["store"] == "PARKNSHOP"
    assert len(out["items"]) == 2


def test_normalize_recovers_json_from_commentary(normalize):
    """Same for a chatty preamble — take the first JSON object and move on."""
    out = normalize("Sure! Here is the receipt:\n\n" + QWEN_REPLY + "\n\nLet me know!")
    assert out["total"] == 88.5
    assert len(out["items"]) == 2


def test_normalize_captures_printed_total(normalize):
    """The receipt's own total is a cross-check, not an item — keep it."""
    out = normalize(QWEN_REPLY)
    assert out["printed_total"] == 88.5
    assert out["line_sum"] == 88.5
    assert out["total"] == 88.5


def test_normalize_price_is_a_line_total(normalize):
    """The single load-bearing convention in the whole schema.

    "3 MUFFIN @ 12.83" prints 38.50 on the line, and that is what `price`
    holds. The frontend sums the column as-is, so if this ever became a unit
    price every multi-quantity receipt would silently under-report.
    """
    out = normalize(QWEN_REPLY)
    assert out["line_sum"] == sum(i["price"] for i in out["items"])
    assert out["line_sum"] != sum(i["price"] * i["qty"] for i in out["items"])


def test_normalize_drops_hallucinated_summary_rows(normalize):
    """A generative model will list TOTAL as an item however firmly it is told
    not to. Left in, it double-counts into line_sum and fakes a clean match."""
    out = normalize(
        """{"total": 88.50, "items": [
             {"name": "MUFFIN", "qty": 3, "price": 38.50},
             {"name": "ICE BLACKCOFFEE", "qty": 2, "price": 50.00},
             {"name": "Subtotal", "qty": 1, "price": 80.00},
             {"name": "TAX", "qty": 1, "price": 8.50},
             {"name": "TOTAL", "qty": 1, "price": 88.50}]}"""
    )
    assert [i["name"] for i in out["items"]] == ["Muffin", "Ice Blackcoffee"]
    assert out["line_sum"] == 88.5


def test_normalize_keeps_items_that_merely_look_like_summaries(normalize):
    """The filter matches whole names only. "Total Wine" is a shop, "Tax
    Service Fee" is a line item, and dropping either would lose real money."""
    out = normalize(
        '{"items": [{"name": "TOTAL WINE MERLOT", "qty": 1, "price": 15.00},'
        ' {"name": "Taxi", "qty": 1, "price": 22.00}]}'
    )
    assert [i["name"] for i in out["items"]] == ["Total Wine Merlot", "Taxi"]
    assert out["line_sum"] == 37.0


def test_normalize_coerces_messy_numbers(normalize):
    """Bare numbers are demanded; currency symbols and separators arrive."""
    out = normalize(
        '{"total": "HK$1,250.00", "items":'
        ' [{"name": "Tea", "qty": "2 x", "price": "$1,250.00"}]}'
    )
    assert out["items"][0]["qty"] == 2
    assert out["items"][0]["price"] == 1250.0
    assert out["printed_total"] == 1250.0


def test_normalize_falls_back_to_line_sum(normalize):
    """With no readable printed total, `total` is the sum of the rows."""
    out = normalize('{"store": "", "date": "", "total": 0, "items":'
                    ' [{"name": "TEA", "qty": 1, "price": "3.50"}]}')
    assert out["printed_total"] is None
    assert out["total"] == 3.5
    assert out["line_sum"] == 3.5


def test_normalize_preserves_mixed_case_names(normalize):
    """All-caps is printer shouting and gets title-cased; anything the model
    already capitalised deliberately is left alone."""
    out = normalize(
        '{"items": [{"name": "iPhone 17 case", "qty": 1, "price": 199},'
        ' {"name": "MCDONALD\'S FRIES", "qty": 1, "price": 12}]}'
    )
    assert [i["name"] for i in out["items"]] == ["iPhone 17 case", "Mcdonald's Fries"]


def test_normalize_survives_junk(normalize):
    """The model can refuse, ramble, or return an empty string; never raise."""
    for junk in ["", "not json at all", "I cannot read this receipt.", "{", "[]",
                 "```json\n{bad json}\n```", {}, [], None]:
        out = normalize(junk)
        assert out["items"] == []
        assert out["total"] == 0
        assert out["store"] == ""


def test_normalize_output_shape_is_stable(normalize):
    """ReceiptTable reads these keys; adding is fine, removing is not."""
    out = normalize(QWEN_REPLY)
    assert set(out) >= {"store", "date", "total", "line_sum", "printed_total", "items"}
    assert set(out["items"][0]) >= {"name", "qty", "price"}


# ==========================================================================
# OFFLINE — the four Modal functions, one section each
#
# funcs.py registers four functions on the app. normalize_output is covered
# above; the rest are covered here. Everything runs through `.local()`, which
# executes the body in-process — no Modal, no GPU, no network.
#
# transcript_receipt is the exception: it needs the model, so what is testable
# offline is its *contract* (the prompt, the image constants) rather than its
# output. The one test that runs the model lives in the live section.
# ==========================================================================

import io  # noqa: E402

try:
    from PIL import Image as PILImage  # noqa: E402
except ImportError:  # pragma: no cover - Pillow is not a gateway dependency
    PILImage = None

needs_pillow = pytest.mark.skipif(PILImage is None, reason="Pillow not installed")

MODAL_FUNCTIONS = {
    "preprocess_image",
    "transcript_receipt",
    "normalize_output",
    "process_receipt",
}

# EXIF tag 274 is Orientation. 1 = as-shot, 3 = 180 deg, 6 and 8 = the two
# quarter turns, which are what a phone writes when you photograph a receipt
# in portrait.
EXIF_ORIENTATION = 274


@pytest.fixture
def funcs_mod():
    import funcs

    return funcs


@pytest.fixture
def preprocess(funcs_mod):
    return funcs_mod.preprocess_image.local


def encode(image, fmt="JPEG", orientation=None):
    """Serialize a PIL image the way an upload would arrive."""
    buf = io.BytesIO()
    if orientation is None:
        image.save(buf, format=fmt)
    else:
        exif = image.getexif()
        exif[EXIF_ORIENTATION] = orientation
        image.save(buf, format=fmt, exif=exif, quality=95)
    return buf.getvalue()


def decode(image_bytes):
    return PILImage.open(io.BytesIO(image_bytes))


# --------------------------------------------------------------------------
# preprocess_image
# --------------------------------------------------------------------------

@needs_pillow
def test_preprocess_returns_an_rgb_png(preprocess):
    out = decode(preprocess(encode(PILImage.new("RGB", (60, 80), "white"))))
    assert out.format == "PNG"
    assert out.mode == "RGB"


@needs_pillow
@pytest.mark.parametrize(
    "orientation,expected",
    [(1, (100, 200)), (3, (100, 200)), (6, (200, 100)), (8, (200, 100))],
)
def test_preprocess_applies_exif_orientation(preprocess, orientation, expected):
    """The failure this guards is silent: PIL does not apply EXIF rotation on
    its own, so a portrait photo reaches the model sideways and the parse comes
    back empty. 6 and 8 are quarter turns and must swap the dimensions."""
    src = PILImage.new("RGB", (100, 200), "white")
    assert decode(preprocess(encode(src, orientation=orientation))).size == expected


@needs_pillow
def test_preprocess_rotates_the_pixels_not_just_the_dimensions(preprocess):
    """A swapped size is necessary but not sufficient — check where the content
    landed. Top half red in portrait must end up on the right after a 90 deg
    turn."""
    src = PILImage.new("RGB", (100, 200), (255, 0, 0))
    src.paste((0, 0, 255), (0, 100, 100, 200))  # bottom half blue
    out = decode(preprocess(encode(src, orientation=6))).convert("RGB")

    w, h = out.size
    assert out.getpixel((3 * w // 4, h // 2))[0] > 200, "red should be on the right"
    assert out.getpixel((w // 4, h // 2))[2] > 200, "blue should be on the left"


@needs_pillow
@pytest.mark.parametrize(
    "given,expected",
    [((4000, 3000), (1920, 1440)), ((3000, 4000), (1440, 1920))],
)
def test_preprocess_caps_the_long_edge_at_1920(preprocess, given, expected):
    """A 12MP phone photo is downsampled by the processor anyway; shipping it
    through the pipeline at full size just costs transfer. Aspect ratio has to
    survive, in both landscape and portrait."""
    assert decode(preprocess(encode(PILImage.new("RGB", given)))).size == expected


@needs_pillow
def test_preprocess_never_upscales(preprocess):
    """Enlarging a small upload invents detail the model would read as text."""
    assert decode(preprocess(encode(PILImage.new("RGB", (800, 600))))).size == (800, 600)


@needs_pillow
@pytest.mark.parametrize("mode", ["RGBA", "L", "P", "CMYK"])
def test_preprocess_converts_any_mode_to_rgb(preprocess, mode):
    """Screenshots arrive RGBA, scans arrive greyscale. None may reach the
    model with an alpha channel or a palette."""
    fmt = "JPEG" if mode == "CMYK" else "PNG"
    out = decode(preprocess(encode(PILImage.new(mode, (50, 60)), fmt=fmt)))
    assert out.mode == "RGB"
    assert out.size == (50, 60)


# --------------------------------------------------------------------------
# transcript_receipt — contract only; the model itself runs in the live section
# --------------------------------------------------------------------------

def test_prompt_names_every_field_of_the_target_schema(funcs_mod):
    """There is no fine-tune behind this schema. The prompt is the schema, so
    a field dropped from it is a field the model stops returning."""
    for field in ("store", "date", "total", "items", "name", "qty", "price"):
        assert field in funcs_mod.PROMPT, f"PROMPT no longer mentions {field!r}"


def test_prompt_pins_the_line_total_rule(funcs_mod):
    """The one convention the frontend cannot recover from: it sums `price`
    as-is. If this drifts to a unit price, every multi-quantity receipt
    under-reports and nothing raises."""
    assert "LINE TOTAL" in funcs_mod.PROMPT
    # the worked example — "3 COFFEE @ 2.50   7.50"
    assert "7.50" in funcs_mod.PROMPT and "2.50" in funcs_mod.PROMPT


def test_prompt_excludes_summary_rows_and_code_fences(funcs_mod):
    prompt = funcs_mod.PROMPT.lower()
    assert "markdown" in prompt, "the model needs telling not to fence the JSON"
    for row in ("subtotal", "tax", "change"):
        assert row in prompt


def test_image_patch_size_matches_qwen3(funcs_mod):
    """qwen_vl_utils defaults image_patch_size to 14 — Qwen2-VL's value.
    Qwen3-VL uses 16, and the default would resize off the token grid."""
    assert funcs_mod.IMAGE_PATCH_SIZE == 16


def test_max_pixels_is_a_whole_number_of_visual_tokens(funcs_mod):
    """One token covers a (patch x merge)^2 block. MAX_PIXELS has to be a
    multiple of that, and under the model's own 16384-token ceiling."""
    token_pixels = (funcs_mod.IMAGE_PATCH_SIZE * 2) ** 2
    assert funcs_mod.MAX_PIXELS % token_pixels == 0
    assert 0 < funcs_mod.MAX_PIXELS // token_pixels <= 16384


# --------------------------------------------------------------------------
# process_receipt — orchestration, with the GPU stage stubbed out
# --------------------------------------------------------------------------

@pytest.fixture
def stub_transcript(funcs_mod, monkeypatch):
    """Stand in for the GPU stage so the pipeline runs without a model."""

    class Stub:
        def __init__(self):
            self.reply = (
                '{"store": "Test Mart", "date": "2026-01-01", "total": 5.0,'
                ' "items": [{"name": "X", "qty": 1, "price": 5.0}]}'
            )
            self.received = None

        def local(self, image_bytes):
            self.received = image_bytes
            return self.reply

    stub = Stub()
    monkeypatch.setattr(funcs_mod, "transcript_receipt", stub)
    return stub


@needs_pillow
def test_process_receipt_runs_all_three_stages(funcs_mod, stub_transcript):
    """preprocess -> transcript -> normalize, returning the frontend schema."""
    out = funcs_mod.process_receipt.local(encode(PILImage.new("RGB", (60, 80))))
    assert out["store"] == "Test Mart"
    assert out["items"] == [{"name": "X", "qty": 1, "price": 5.0}]
    assert out["printed_total"] == 5.0
    assert out["line_sum"] == 5.0


@needs_pillow
def test_process_receipt_hands_the_model_preprocessed_bytes(funcs_mod, stub_transcript):
    """The model must see the EXIF-corrected PNG, not the original upload —
    otherwise preprocess_image is decorative."""
    funcs_mod.process_receipt.local(encode(PILImage.new("RGB", (60, 80))))
    assert stub_transcript.received.startswith(b"\x89PNG\r\n\x1a\n")


@needs_pillow
def test_process_receipt_survives_a_junk_generation(funcs_mod, stub_transcript):
    """A refusal or a truncated reply must come back empty, not raise — a GPU
    exception would surface to the browser as a 500 after a 60s wait."""
    stub_transcript.reply = "I'm sorry, I can't read that receipt."
    out = funcs_mod.process_receipt.local(encode(PILImage.new("RGB", (60, 80))))
    assert out["items"] == []
    assert out["total"] == 0


# --------------------------------------------------------------------------
# Modal deployment config — cheap guards on expensive mistakes
# --------------------------------------------------------------------------

def test_every_function_is_registered_on_the_app(funcs_mod):
    """The gateway spawns process_receipt by direct reference; a function that
    silently stops registering fails only at deploy time."""
    from config import app

    assert MODAL_FUNCTIONS <= set(app.registered_functions)


def test_gateway_and_gpu_functions_share_one_app(gw):
    """Why `modal deploy backend/gateway.py` covers both halves: importing
    funcs registers the GPU functions on the same app the gateway serves from.
    Split them across two apps and the deploy silently ships half the system.
    """
    from config import app

    registered = set(app.registered_functions)
    assert "fastapi_app" in registered, "the gateway is not on this app"
    assert MODAL_FUNCTIONS <= registered


@pytest.mark.parametrize("name", ["transcript_receipt", "process_receipt"])
def test_gpu_functions_pin_the_l4(funcs_mod, name):
    """gpu="any" could land on a T4: 16GB and no bf16 support."""
    assert getattr(funcs_mod, name).spec.gpus == "L4"


@pytest.mark.parametrize("name", ["transcript_receipt", "process_receipt"])
def test_gpu_functions_mount_the_model_cache(funcs_mod, name):
    """Without the volume, every cold start re-downloads ~8GB of weights."""
    assert "/root/models" in getattr(funcs_mod, name).spec.volumes


@pytest.mark.parametrize("name", ["preprocess_image", "normalize_output"])
def test_cpu_functions_request_no_gpu(funcs_mod, name):
    """Resizing an image and parsing JSON on an L4 is billed at $0.80/hr."""
    assert getattr(funcs_mod, name).spec.gpus is None


def test_the_model_is_cached_between_calls(funcs_mod):
    """setup() loads ~8GB. Drop the lru_cache and every single request reloads
    it, turning a 3s warm parse back into a cold start."""
    assert funcs_mod.setup.cache_info().maxsize == 1
