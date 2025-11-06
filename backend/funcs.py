import modal
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import io, re, os
import torch
from transformers import DonutProcessor, VisionEncoderDecoderModel
from functools import lru_cache
from modal import Secret

# Modal App and Docker Image
app = modal.App('receipt-parsing-functions')

inference_image = modal.Image.debian_slim(python_version="3.12").pip_install_from_requirements(
    'requirements.txt'
)

# Declare the model name, no need to add a revision so HuggingFace always gives the latest model
MODEL_NAME = "debu-das/donut_receipt_v1.20"

# Declare the prompt DONUT should use
PROMPT = """<s_cord-v2>
You are extracting structured data from a receipt image.
Return the result as a clean JSON object with exactly these keys: {store, date, total, items}.
Each item in 'items' must be an object with keys {name, qty, price}.
Do NOT include extra text, labels, or explanations.

Example 1:
{
    "store": "Target",
    "date": "2023-08-02",
    "total": 23.45,
    "items": [
        {"name": "Milk", "qty": 1, "price": 3.29},
        {"name": "Bread", "qty": 2, "price": 4.98},
        {"name": "Cereal", "qty": 1, "price": 5.19}
    ]
}

Example 2:
{
    "store": "Walmart Supercenter",
    "date": "2024-12-18",
    "total": 42.69,
    "items": [
        {"name": "Apples", "qty": 3, "price": 5.99},
        {"name": "Bananas", "qty": 2, "price": 3.49},
        {"name": "Toothpaste", "qty": 1, "price": 4.99},
        {"name": "Soda", "qty": 6, "price": 14.22}
    ]
}

Now extract the information for this receipt and return only the JSON result:
<s_answer>"""


# API key added via Modal secret
SECRET_NAME = "RECEIPT_PARSER_SECRET"
API_KEY_ENV = "RECEIPT_API_KEY"

def verify_internal_key(provided_key: str):
    """Ensure only authorized callers can use these functions"""
    expected_key = os.environ.get(API_KEY_ENV)
    if provided_key != expected_key:
        raise PermissionError("Unauthorized: Invalid internal API key.")

@lru_cache(maxsize=1)
def setup():
    # Load the pretrained Donut model
    processor = DonutProcessor.from_pretrained(MODEL_NAME, use_fast = True)
    model = VisionEncoderDecoderModel.from_pretrained(MODEL_NAME)

    # Tell the model what to run on 
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    return processor, model, device

# Cache the DONUT model to reduce cost of cold start
model_cache = modal.Volume.from_name("hf-hub-cache", create_if_missing=True)

MODEL_CACHE_PATH = "/root/models"
inference_image = inference_image.env(
    {"HF_HUB_CACHE": MODEL_CACHE_PATH,
     "HF_HUB_ENABLE_HF_TRANSFER": "0"}
)

# Func to preprocess receipt
@app.function(image=inference_image)
def preprocess_image(image_bytes: bytes) -> bytes:
    """
    Light preprocessing for receipts:
        - auto-orient using EXIF
        - mild brightness/contrast adjustment
        - resize (preserve aspect ratio, limit to 1280px)
        - convert to RGB
    """
    from PIL import ImageOps, ImageEnhance, ImageStat, ImageFilter
    import io

    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)  # auto-orient (fix sideways receipts)

    # Ensure RGB
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Adjust brightness and contrast gently
    stat = ImageStat.Stat(image)
    avg_brightness = sum(stat.mean) / len(stat.mean)
    if avg_brightness < 100:
        image = ImageEnhance.Brightness(image).enhance(1.2)
    image = ImageEnhance.Contrast(image).enhance(1.1)

    # Slight unsharp mask for clarity (optional)
    image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

    # Resize if too large (keep aspect ratio)
    max_size = 1280
    if max(image.size) > max_size:
        ratio = max_size / max(image.size)
        new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    # Save to bytes
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()



@app.function(
    image=inference_image, 
    gpu="any",
    retries=3,
    volumes={MODEL_CACHE_PATH: model_cache},
    secrets=[Secret.from_name(SECRET_NAME)]
)
def transcript_receipt(image_bytes: bytes, api_key: str):
    """Function to transcript a receipt and return the contents in JSON"""
    verify_internal_key(api_key)

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
    Normalize and clean Donut JSON output for consistency.
    """
    # Handle case where Donut returns a list
    if isinstance(raw_json, list):
        if len(raw_json) > 0 and isinstance(raw_json[0], dict):
            raw_json = raw_json[0]
        else:
            return {"error": "Invalid model output format"}

    def clean_price(value):
        if isinstance(value, str):
            value = re.sub(r"[^\d.]", "", value)
            return float(value) if value else None
        return value

    return {
        "store": raw_json.get("store", "").strip().title(),
        "date": raw_json.get("date", "").replace("/", "-"),
        "total": clean_price(raw_json.get("total")),
        "items": [
            {
                "name": i.get("name", "").title(),
                "price": clean_price(i.get("price")),
                "qty": int(i.get("quantity", 1))
            }
            for i in raw_json.get("items", [])
        ]
    }


@app.function(image=inference_image)
def get_status():
    gpu = torch.cuda.is_available()
    return {
        "status": "ready",
        "gpu": gpu,
        "device": "cuda" if gpu else "cpu",
        "model": MODEL_NAME
    }

@app.function(
    image=inference_image, 
    gpu="any",
    retries=3,
    volumes={MODEL_CACHE_PATH: model_cache},
    secrets=[Secret.from_name(SECRET_NAME)]
)
def process_receipt(image_bytes: bytes, api_key: str):
    """Full pipeline: preprocess -> transcript -> normalize"""
    verify_internal_key(api_key)

    preprocessed = preprocess_image.local(image_bytes)
    raw = transcript_receipt.local(image_bytes, api_key)
    normalized = normalize_output.local(raw)
    return raw
