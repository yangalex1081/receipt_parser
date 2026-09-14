"""Score a prompt against the hand-labelled receipts in test_photos/.

The point of this file is to make prompt changes measurable. Before it, the loop
was: edit PROMPT, `modal deploy`, upload one photo, squint at the table. That
costs a GPU invocation per idea and produces no comparable number, which is why
the honest commit message for the last round of tuning was "updated many things
to try and get better performance".

Two things keep the numbers meaningful:

  The pipeline is the real one. preprocess_image and normalize_output are
  imported from funcs.py and run through `.local()`, so a prompt that wins here
  wins because the deployed normalizer can parse it, not because the harness is
  more forgiving than production.

  The model matches. `qwen3-vl:4b-instruct-bf16` is the same checkpoint and the
  same dtype production loads, so local scores are meaningful in absolute terms,
  not just as a ranking. Confirm a winner on Modal before shipping it, but the
  numbers here are not a different model's numbers.

  Do not switch to the bare `qwen3-vl:4b` tag. That resolves to the *Thinking*
  variant, which spends the entire token budget on hidden reasoning and returns
  an empty string — and `think: false` does not suppress it. Production runs
  Qwen3-VL-4B-Instruct; the tag has to say `instruct`.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import requests
from PIL import Image

EVAL_DIR = Path(__file__).resolve().parent
REPO = EVAL_DIR.parent.parent
PHOTOS = REPO / "test_photos"
TRUTH = EVAL_DIR / "ground_truth"
PROMPTS = EVAL_DIR / "prompts"

# funcs.py imports config.py as a top-level module, the way Modal containers see
# it, so backend/ has to be importable directly rather than as a package.
sys.path.insert(0, str(REPO / "backend"))

import funcs  # noqa: E402

OLLAMA = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:4b-instruct-bf16"

# The deployed app, for the --modal backend.
MODAL_APP = "receipt-parser"

# A predicted row is credited to a truth row when the names are at least this
# similar. Deliberately loose: this harness is measuring whether the model
# understood the *task* (which rows are items, what number goes in `price`), and
# a name off by an OCR character is not the failure being hunted. Price is then
# compared exactly, so a loose name gate cannot launder a wrong number.
NAME_MATCH = 0.6

# Rows that are not purchases. Every one of these appearing in `items` is a
# double-count on the split, so they are worth counting separately rather than
# letting them disappear into the precision figure.
JUNK = re.compile(
    r"\b(sub-?total|total|tax|vat|gst|pb1|service|tip|gratuity|change|discount"
    r"|coupon|rounding|balance|amount\s+due|payment|cash|card|visa|mastercard"
    r"|amex|debit|credit|tender|due)\b",
    re.I,
)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


# --------------------------------------------------------------------------
# Model call
# --------------------------------------------------------------------------


def prepare_image(path: Path, cap: bool = True) -> bytes:
    """Put the image through production preprocessing, then production's cap.

    preprocess_image handles EXIF rotation and the 1920px long-edge cap. On
    Modal the processor then downsamples to MAX_PIXELS; Ollama has no equivalent
    knob, so that second step is applied here explicitly. Without it the local
    model would read a sharper image than the deployed one and every local score
    would be optimistic.

    `cap=False` stops after preprocessing, which is what the --modal backend
    wants: it hands the bytes to the real transcript_receipt, whose processor
    applies MAX_PIXELS itself. Capping first would resize twice and score the
    deployment against an image it would never actually be sent.
    """
    raw = funcs.preprocess_image.local(path.read_bytes())
    if not cap:
        return raw

    image = Image.open(io.BytesIO(raw))
    w, h = image.size
    if w * h > funcs.MAX_PIXELS:
        scale = (funcs.MAX_PIXELS / (w * h)) ** 0.5
        image = image.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS
        )

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def call_ollama(
    prompt: str, image_bytes: bytes, model: str, timeout: int = 900
) -> tuple[str, dict]:
    """Return the reply and enough metadata to tell a bad prompt from a cut-off one.

    `done_reason` is the field that matters. A reply truncated at the token cap
    scores identically to a reply the model never started — both parse to zero
    items — and without this the harness reports "the prompt failed" when the
    real cause is MAX_NEW_TOKENS being too small for a 25-row receipt.
    """
    response = requests.post(
        OLLAMA,
        json={
            "model": model,
            "prompt": prompt,
            # Belt and braces: an Instruct checkpoint ignores this, but it makes
            # a misconfigured thinking tag fail loudly rather than silently.
            "think": False,
            "images": [base64.b64encode(image_bytes).decode()],
            "stream": False,
            "options": {
                # Greedy, matching do_sample=False in transcript_receipt. Without
                # this a prompt could win a run on luck and lose the rerun.
                "temperature": 0,
                "num_predict": funcs.MAX_NEW_TOKENS,
            },
        },
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("response", ""), {
        "done_reason": body.get("done_reason"),
        "output_tokens": body.get("eval_count"),
        "prompt_tokens": body.get("prompt_eval_count"),
        "thinking_chars": len(body.get("thinking") or ""),
    }


def call_modal(
    prompt: str, image_bytes: bytes, model: str, timeout: int = 900
) -> tuple[str, dict]:
    """Score the deployed GPU function instead of the local copy.

    `prompt` and `model` are accepted to match call_ollama's signature and then
    ignored, because transcript_receipt takes only image bytes — the prompt is
    funcs.PROMPT, baked in at deploy time. So this backend answers one question:
    how well does what is *currently deployed* do on the labelled set? To score
    a candidate prompt this way you would have to deploy it first, which is the
    loop the local backend exists to avoid.

    Ollama's per-reply metadata has no equivalent here, so a truncated reply is
    not flagged. It shows up as a parse failure instead.
    """
    import modal

    fn = modal.Function.from_name(MODAL_APP, "transcript_receipt")
    reply = fn.remote(image_bytes)

    if not isinstance(reply, str):
        raise TypeError(
            f"transcript_receipt returned {type(reply).__name__}, not str — the "
            "deployed build is stale; run `modal deploy backend/gateway.py`"
        )
    return reply, {}


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


@dataclass
class Score:
    photo: str
    parsed: bool
    n_truth: int
    n_pred: int
    correct: int  # name matched AND price exact
    name_only: int  # name matched, price wrong
    qty_ok: int
    junk: int
    total_ok: bool | None
    store_ok: bool | None
    date_ok: bool | None
    seconds: float
    truncated: bool = False
    output_tokens: int | None = None
    raw: str = ""
    misses: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.correct / self.n_truth if self.n_truth else 0.0

    @property
    def precision(self) -> float:
        return self.correct / self.n_pred if self.n_pred else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def _match(pred_items, truth_items):
    """Greedy highest-similarity-first pairing, each row used at most once.

    Greedy rather than optimal: receipts contain genuine duplicate rows (four
    STKO SUNFLWR on the Walmart scan, two Soju on the bar tab) and the goal is
    to count how many were reproduced, not to find the single best assignment.
    """
    pairs = sorted(
        (
            (_sim(p["name"], t["name"]), i, j)
            for i, p in enumerate(pred_items)
            for j, t in enumerate(truth_items)
        ),
        key=lambda x: -x[0],
    )
    used_pred, used_truth, matched = set(), set(), []
    for sim, i, j in pairs:
        if sim < NAME_MATCH or i in used_pred or j in used_truth:
            continue
        used_pred.add(i)
        used_truth.add(j)
        matched.append((pred_items[i], truth_items[j]))
    unmatched_truth = [t for j, t in enumerate(truth_items) if j not in used_truth]
    return matched, unmatched_truth


def _money_eq(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 0.011
    except (TypeError, ValueError):
        return False


def score_one(
    photo: str, raw: str, truth: dict, seconds: float, meta: dict | None = None
) -> Score:
    parsed = funcs.normalize_output.local(raw)
    pred_items = parsed.get("items") or []
    truth_items = truth["items"]

    matched, missed = _match(pred_items, truth_items)
    correct = sum(1 for p, t in matched if _money_eq(p.get("price"), t["price"]))
    qty_ok = sum(1 for p, t in matched if p.get("qty") == t["qty"])

    def field_ok(key, fuzzy=False):
        want = truth.get(key)
        if want is None:  # unreadable on the receipt itself — not scored
            return None
        got = parsed.get(key) or ""
        return _sim(got, want) >= NAME_MATCH if fuzzy else _norm(got) == _norm(want)

    return Score(
        photo=photo,
        # normalize_output returns the empty shape rather than raising, so an
        # unparseable reply looks like a zero-item receipt. Distinguish them.
        parsed=bool(pred_items) or bool(parsed.get("total")),
        n_truth=len(truth_items),
        n_pred=len(pred_items),
        correct=correct,
        name_only=len(matched) - correct,
        qty_ok=qty_ok,
        junk=sum(1 for p in pred_items if JUNK.search(str(p.get("name", "")))),
        total_ok=(
            None
            if truth.get("total") is None
            else _money_eq(parsed.get("total"), truth["total"])
        ),
        store_ok=field_ok("store", fuzzy=True),
        date_ok=field_ok("date"),
        seconds=seconds,
        truncated=(meta or {}).get("done_reason") == "length",
        output_tokens=(meta or {}).get("output_tokens"),
        raw=raw,
        misses=[f"{t['name']} @ {t['price']}" for t in missed],
    )


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_cases(only: list[str] | None = None):
    cases = []
    for photo in sorted(PHOTOS.iterdir()):
        if photo.name.startswith("."):
            continue
        truth_path = TRUTH / f"{photo.stem}.json"
        if not truth_path.exists():
            continue
        if only and photo.stem not in only:
            continue
        cases.append((photo, json.loads(truth_path.read_text())))
    return cases


def load_prompts(only: list[str] | None = None):
    out = {}
    for path in sorted(PROMPTS.glob("*.txt")):
        if only and path.stem not in only:
            continue
        out[path.stem] = path.read_text().strip()
    return out


def run(
    prompt_name: str,
    prompt: str,
    cases,
    model: str,
    verbose: bool = False,
    caller=call_ollama,
):
    scores = []
    for photo, truth in cases:
        image = prepare_image(photo, cap=caller is call_ollama)
        start = time.monotonic()
        try:
            raw, meta = caller(prompt, image, model)
        except Exception as exc:  # noqa: BLE001 - a dead model should not kill the sweep
            print(f"  {photo.stem}: request failed — {exc}")
            raw, meta = "", {}
        elapsed = time.monotonic() - start

        s = score_one(photo.stem, raw, truth, elapsed, meta)
        scores.append(s)
        if verbose:
            print(
                f"  {s.photo:<22} F1 {s.f1:.2f}  "
                f"{s.correct}/{s.n_truth} correct, {s.n_pred} returned, "
                f"junk {s.junk}, total {'ok' if s.total_ok else 'MISS'}"
                f"{'  [TRUNCATED]' if s.truncated else ''}  "
                f"{s.seconds:.0f}s"
            )
    return scores
