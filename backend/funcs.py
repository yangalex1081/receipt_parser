"""GPU inference functions: preprocess -> Qwen3-VL transcription -> normalize."""

import io
from functools import lru_cache

from config import (
    INFERENCE_GPU,
    MODEL_CACHE_PATH,
    MODEL_NAME,
    app,
    inference_image,
    model_cache,
)

# These only exist inside containers built on inference_image. Importing them at
# module scope would break the gateway, which imports this module to reference
# process_receipt but runs on a slim image without the ML stack.
with inference_image.imports():
    import cv2  # noqa: F401  (loaded for libgl parity with prior image)
    import numpy as np  # noqa: F401
    import torch
    from PIL import Image, ImageOps
    from qwen_vl_utils import process_vision_info
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

# Qwen3-VL's ViT uses 16px patches with a 2x2 spatial merge, so one visual token
# covers a 32x32 pixel block. qwen_vl_utils defaults to 14 (Qwen2-VL's patch
# size); passing the right value keeps its resize on the grid the processor
# expects rather than making the processor resize a second time.
IMAGE_PATCH_SIZE = 16
_TOKEN_PIXELS = (IMAGE_PATCH_SIZE * 2) ** 2

# Cap the image at ~1600 visual tokens. The model's own ceiling is 16384, which
# for a receipt is mostly spent encoding blank paper: 1600 tokens is roughly
# 1280x1000, enough that small print stays legible, and it keeps prefill (and
# therefore the warm parse latency) bounded.
MAX_PIXELS = 1600 * _TOKEN_PIXELS

# Long receipts run to ~40 items; 1024 tokens covers that with margin.
MAX_NEW_TOKENS = 1024

# Unlike Donut, this model reads instructions — the schema below is the only
# thing defining the output, so it has to be exact.
#
# The load-bearing rule is `price`: it is the LINE TOTAL for the row, not the
# unit price. The frontend sums it directly and never multiplies by qty, so a
# model that reports unit prices silently under-reports every multi-quantity
# receipt. The examples exist to pin that down.
PROMPT = """Extract this receipt as JSON. Reply with the JSON object only — no \
markdown fences, no explanation.

Schema:
{
  "store": "merchant name as printed, or \\"\\" if unreadable",
  "date": "purchase date as YYYY-MM-DD, or \\"\\" if unreadable",
  "total": grand total printed on the receipt, as a number,
  "items": [
    {"name": "item name as printed", "qty": integer, "price": line total}
  ]
}

Rules:
- "price" is the LINE TOTAL for that row — the amount printed at the right of \
the line. If the receipt shows "3 COFFEE @ 2.50   7.50", then qty is 3 and \
price is 7.50, not 2.50.
- Where no quantity is printed, qty is 1 and price is that line's amount.
- Copy names exactly as printed. Do not translate them, expand abbreviations, \
correct spelling, or add items you cannot see.
- Do NOT put subtotal, tax, service charge, tip, discount, rounding, payment or \
change lines in "items". The grand total goes in "total" and nowhere else.
- Write numbers bare: no currency symbols, no thousands separators, a period \
for the decimal point.
- Use "" for a string you cannot read and 0 for a number you cannot read. \
Never guess."""


@lru_cache(maxsize=1)
def setup():
    processor = AutoProcessor.from_pretrained(MODEL_NAME)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL_NAME,
        # bf16 halves the 8GB of weights and matches what the checkpoint was
        # trained in. Guarded because CPU bf16 matmuls are painfully slow, and
        # this falls back to CPU when run outside a GPU container.
        dtype=torch.bfloat16 if device == "cuda" else torch.float32,
        # Places weights on the device as they load, rather than materialising
        # the whole model in host RAM first and then copying it across.
        device_map=device,
    )
    model.eval()

    return processor, model


@app.function(image=inference_image)
def preprocess_image(image_bytes: bytes) -> bytes:
    """Minimal, orientation-correcting preprocessing.

    The processor already resizes and normalizes to what the model expects, so
    there is little to gain here and real damage to be done: contrast pushes and
    unsharp masks alter the glyph shapes the vision encoder was trained on.

    What does matter is EXIF orientation. Phone cameras record rotation in
    metadata rather than rotating pixels, and PIL does not apply it — so a
    receipt photographed in portrait can reach the model sideways. That alone
    can empty out a parse.
    """
    image = Image.open(io.BytesIO(image_bytes))

    # Apply the EXIF rotation before dropping the metadata via convert().
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")

    # Cap the long edge. The processor downsamples to MAX_PIXELS anyway; feeding
    # a 12MP phone photo through the volume mount first just costs transfer.
    max_size = 1920
    w, h = image.size
    scale = min(max_size / max(w, h), 1.0)
    if scale < 1.0:
        image = image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@app.function(
    image=inference_image,
    gpu=INFERENCE_GPU,
    retries=3,
    volumes={MODEL_CACHE_PATH: model_cache},
)
def transcript_receipt(image_bytes: bytes) -> str:
    """Run the VLM over one receipt and return its raw reply.

    The reply is a string, not a dict: it is whatever the model generated, and
    parsing it is normalize_output's job. Keeping the split means a malformed
    generation is a normalization problem with a recorded input rather than an
    exception thrown inside a GPU container.
    """
    processor, model = setup()

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image, "max_pixels": MAX_PIXELS},
                {"type": "text", "text": PROMPT},
            ],
        }
    ]

    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    image_inputs, _video_inputs = process_vision_info(
        messages, image_patch_size=IMAGE_PATCH_SIZE
    )
    inputs = processor(
        text=[text], images=image_inputs, padding=True, return_tensors="pt"
    ).to(model.device)

    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            # Transcription, not composition: sampling here would only invent
            # prices. Greedy also makes a bad parse reproducible.
            do_sample=False,
        )

    # generate() returns prompt + completion; keep only what was generated.
    completion = generated[0][inputs.input_ids.shape[1] :]

    return processor.decode(
        completion, skip_special_tokens=True, clean_up_tokenization_spaces=False
    ).strip()


@app.function(image=inference_image)
def normalize_output(raw):
    """Turn the model's reply into the schema the frontend consumes:

    {
      "store": str,
      "date": str,
      "total": float,
      "line_sum": float,
      "printed_total": float | None,
      "items": [{"name": str, "qty": int, "price": float}, ...]
    }

    The prompt asks for almost exactly this, so most of the work is coercion and
    distrust rather than translation. Two things earn their keep: pulling JSON
    out of a reply that wrapped it in prose or a code fence, and keeping the
    receipt's printed total separate from the sum of the rows.
    """

    import json
    import re

    def extract_json(text):
        """Extract and parse the first JSON object from messy text.

        The model is told to return bare JSON and usually does, but "usually"
        is the operative word — ```json fences and a leading sentence of
        commentary are the two failure modes worth surviving.
        """
        if not isinstance(text, str):
            return None
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except Exception:
                        break
        return None

    def to_float(val):
        if val is None:
            return 0.0
        if isinstance(val, bool):
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        s = re.sub(r"[^0-9,.\-]", "", str(val))
        s = s.replace(",", "")
        if s.endswith("."):
            s = s[:-1]
        try:
            return float(s)
        except Exception:
            return 0.0

    def to_int(val):
        if val is None:
            return 1
        if isinstance(val, bool):
            return 1
        if isinstance(val, int):
            return val
        m = re.search(r"(\d+)", str(val))
        return int(m.group(1)) if m else 1

    # A generative model will occasionally list the summary lines as items
    # despite being told not to, which would double-count them into line_sum.
    # Matched on the whole name only — "Total Wine Merlot" and "Taxi" are real
    # items. The list is deliberately short and errs towards keeping rows: a
    # payment line that slips through shows up as a totals mismatch the user
    # can see, whereas a real item dropped here just quietly vanishes.
    SUMMARY_ROWS = {
        "subtotal", "sub total", "total", "grand total", "balance",
        "amount due", "tax", "sales tax", "vat", "gst", "service charge",
        "tip", "gratuity", "discount", "rounding", "change", "cash", "payment",
    }

    # --- Parse ---------------------------------------------------------------
    data = extract_json(raw) if isinstance(raw, str) else raw
    if isinstance(data, list):
        # A bare array of items, without the wrapper object.
        data = {"items": data}
    if not isinstance(data, dict):
        data = {}

    # --- Items ---------------------------------------------------------------
    items_src = data.get("items")
    if not isinstance(items_src, list):
        items_src = []

    items = []
    for d in items_src:
        if not isinstance(d, dict):
            continue

        name = str(d.get("name") or "").strip()
        if re.sub(r"[^a-z ]", "", name.lower()).strip() in SUMMARY_ROWS:
            continue

        # Receipt printers are all-caps. Title-case those so the table is
        # readable, but leave anything already mixed-case as the model read it.
        if name.isupper():
            name = re.sub(r"[\w']+", lambda m: m.group(0).capitalize(), name)

        items.append(
            {
                "name": name,
                "qty": to_int(d.get("qty")),
                # The line total for the row, never the unit price — the
                # frontend sums this column as-is. See PROMPT.
                "price": to_float(d.get("price")),
            }
        )

    # --- Totals --------------------------------------------------------------
    #
    # The printed total and the sum of the rows are two independent readings of
    # the same number. Reporting both lets the frontend flag a disagreement,
    # which is what a missed — or, now that the model is generative, an
    # invented — line item looks like.
    printed_total = to_float(data.get("total")) or None

    line_sum = sum(i["price"] for i in items)

    return {
        "store": str(data.get("store") or "").strip(),
        "date": str(data.get("date") or "").strip(),
        # What the receipt says when we could read it, else the sum of the rows.
        "total": printed_total if printed_total else line_sum,
        "line_sum": line_sum,
        "printed_total": printed_total,
        "items": items,
    }


@app.function(
    image=inference_image,
    gpu=INFERENCE_GPU,
    retries=3,
    volumes={MODEL_CACHE_PATH: model_cache},
)
def process_receipt(image_bytes: bytes):
    """Full pipeline: preprocess -> transcript -> normalize

    Runs the three stages with .local() so they share one GPU container rather
    than making three remote hops.
    """
    preprocessed = preprocess_image.local(image_bytes)
    raw = transcript_receipt.local(preprocessed)
    normalized = normalize_output.local(raw)
    return normalized
