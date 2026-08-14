"""GPU inference functions: preprocess -> Donut transcription -> normalize."""

import io
import re
from functools import lru_cache

from config import (
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
    from PIL import Image, ImageEnhance, ImageFilter
    from transformers import DonutProcessor, VisionEncoderDecoderModel

# Declare the prompt DONUT should use
PROMPT = """<s_cord-v2>
You are reading a receipt and must extract the purchased items.

Return the result as a JSON object with a single key "menu".
Each element in "menu" must have:
- "nm" for the item name,
- "cnt" for the quantity,
- "price" for the item price.

Do not include store name, date, total, or extra explanations.

### Example 1
{
  "menu": [
    {"nm": "ICE BLACKCOFFEE", "cnt": "2", "price": "5000"},
    {"nm": "LATTE", "cnt": "1", "price": "4500"},
    {"nm": "MUFFIN", "cnt": "3", "price": "9000"}
  ]
}

### Example 2
{
  "menu": [
    {"nm": "NASI GORENG", "cnt": "1", "price": "42000"},
    {"nm": "ICED TEA", "cnt": "2", "price": "12000"},
    {"nm": "CHICKEN SATAY", "cnt": "1", "price": "38000"}
  ]
}

Now extract and return only the JSON result for this receipt:
<s_answer>"""


@lru_cache(maxsize=1)
def setup():
    # Load the pretrained Donut model
    processor = DonutProcessor.from_pretrained(MODEL_NAME, use_fast=True)
    model = VisionEncoderDecoderModel.from_pretrained(MODEL_NAME)

    # Tell the model what to run on
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    return processor, model, device


# Func to preprocess receipt
@app.function(image=inference_image)
def preprocess_image(image_bytes: bytes) -> bytes:
    """
    Light, Donut-friendly preprocessing:
      - Keep RGB
      - Optional gentle contrast stretch
      - Resize (preserve aspect ratio)
      - Mild sharpening
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # 1️⃣ Gentle contrast — 1.2x instead of 2.0x
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.8)

    # 2️⃣ Resize — ensure longest side ≤ 1280px
    max_size = 1280
    w, h = image.size
    scale = min(max_size / max(w, h), 1.0)
    if scale < 1.0:
        new_size = (int(w * scale), int(h * scale))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    # 3️⃣ Mild sharpening — avoids over-edge artifacts
    image = image.filter(ImageFilter.UnsharpMask(radius=0.8, percent=100, threshold=3))

    # Save
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@app.function(
    image=inference_image,
    gpu="any",
    retries=3,
    volumes={MODEL_CACHE_PATH: model_cache},
)
def transcript_receipt(image_bytes: bytes):
    """Function to transcript a receipt and return the contents in JSON"""
    # Load model and processor
    processor, model, device = setup()

    # Load PIL image from bytes
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Prepare encoder inputs
    pixel_values = processor(image, return_tensors="pt").pixel_values

    # Prepare decoder inputs
    task_prompt = PROMPT
    decoder_input_ids = processor.tokenizer(
        task_prompt, add_special_tokens=False, return_tensors="pt"
    ).input_ids

    # Generate answer
    outputs = model.generate(
        pixel_values.to(device),
        decoder_input_ids=decoder_input_ids.to(device),
        max_length=model.decoder.config.max_position_embeddings,
        pad_token_id=processor.tokenizer.pad_token_id,
        eos_token_id=processor.tokenizer.eos_token_id,
        use_cache=True,
        num_beams=1,
        bad_words_ids=[[processor.tokenizer.unk_token_id]],
        return_dict_in_generate=True,
    )

    # Postprocess
    sequence = processor.batch_decode(outputs.sequences)[0]
    sequence = sequence.replace(processor.tokenizer.eos_token, "").replace(
        processor.tokenizer.pad_token, ""
    )
    sequence = re.sub(r"<.*?>", "", sequence, count=1).strip()  # remove first task start token

    return processor.token2json(sequence)


@app.function(image=inference_image)
def normalize_output(raw_json):
    """
    Robustly normalize Donut/CORD-style output into frontend schema:
    {
      "store": "",
      "date": "",
      "total": <float>,
      "items": [{"name": str, "qty": int, "price": float}, ...]
    }
    Handles strings, dicts with text_sequence/menu/items, or lists.
    """

    import json, re

    def extract_json(text):
        """Extract and parse the first JSON object from messy text."""
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
                        return json.loads(text[start:i+1])
                    except Exception:
                        break
        return None

    def to_float(val):
        if val is None:
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
        if isinstance(val, int):
            return val
        s = str(val).lower()
        m = re.search(r"(\d+)", s)
        return int(m.group(1)) if m else 1

    # --- Step 1: Parse and clean input ---
    if isinstance(raw_json, dict) and "text_sequence" in raw_json:
        parsed = extract_json(raw_json["text_sequence"])
        raw_json = parsed or raw_json
    elif isinstance(raw_json, str):
        parsed = extract_json(raw_json)
        raw_json = parsed or {}

    # --- Step 2: Locate items container ---
    if isinstance(raw_json, list):
        items_src = raw_json
    elif isinstance(raw_json, dict):
        items_src = (
            raw_json.get("menu")
            or raw_json.get("items")
            or ([raw_json] if any(k in raw_json for k in ("nm", "name", "description", "price")) else [])
        )
    else:
        items_src = []

    # --- Step 3: Normalize item fields ---
    items = []
    for d in items_src:
        if not isinstance(d, dict):
            continue
        if set(d.keys()) <= {"sub_total", "total", "subtotal_price", "tax_price", "service_price"}:
            continue

        name = d.get("nm") or d.get("name") or d.get("description") or ""
        qty = d.get("cnt") or d.get("qty") or d.get("quantity") or 1
        price = d.get("price") or d.get("total") or 0

        items.append({
            "name": str(name).strip().title(),
            "qty": to_int(qty),
            "price": to_float(price)
        })

    total = sum(i["price"] for i in items)
    return {"store": "", "date": "", "total": total, "items": items}


@app.function(image=inference_image)
def get_status():
    gpu = torch.cuda.is_available()
    return {
        "status": "ready",
        "gpu": gpu,
        "device": "cuda" if gpu else "cpu",
        "model": MODEL_NAME,
    }


@app.function(
    image=inference_image,
    gpu="any",
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
