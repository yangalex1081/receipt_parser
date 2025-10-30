# This file creates and runs the functions to actually transcript a receipt via Modal

import modal
from PIL import Image, ImageEnhance
import io, re
import torch
from transformers import DonutProcessor, VisionEncoderDecoderModel
from functools import lru_cache

# Modal App and Docker Image
app = modal.App('receipt-parsing-functions')

inference_image = modal.Image.debian_slim(python_version="3.12").pip_install_from_requirements(
    'requirements.txt'
)

# Declare the model name, no need to add a revision so HuggingFace always gives the latest model
MODEL_NAME = "debu-das/donut_receipt_v1.20"

# Declare the prompt DONUT should use
PROMPT = (
    "<s_cord-v2> "
    "Return a JSON object with exactly these keys: "
    "{store, date, total, items}. "
    "The 'items' field must be an array of objects with keys {name, price, quantity}. "
    "Do not include extra text or explanations. <s_answer>"
)


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
@app.function(image = inference_image)
def preprocess_image(image_bytes: bytes) -> bytes:
    """
    Takes the raw bytes of an image and then:
        grayscales
        boosts contrast
        resizes
    to output RGB bytes
    """

    # Grayscale
    image = Image.open(io.BytesIO(image_bytes)).convert("L")  

    # Increase contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    # Resize if needed (max 1024 pixels on long side)
    max_size = 1024
    ratio = min(max_size / image.size[0], max_size / image.size[1])
    new_size = tuple(int(x * ratio) for x in image.size)
    image = image.resize(new_size)

    # Donut expects RGB
    image = image.convert("RGB")

    # Save to bytes to pass between Modal functions
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()

@app.function(
    image=inference_image, 
    gpu="any",
    retries=3,
    volumes={MODEL_CACHE_PATH: model_cache}
)
def transcript_receipt(image_bytes: bytes):
    """
    Function to transcript a receipt and return the contents in JSON
    """


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
def normalize_output(raw_json: dict) -> dict:
    """
    Normalize and clean Donut JSON output for consistency.
    """
    def clean_price(value):
        if isinstance(value, str):
            value = re.sub(r"[^\d.]", "", value)
            return float(value) if value else None
        return value

    return {
        "store": raw_json.get("store_name", "").strip().title(),
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
    volumes={MODEL_CACHE_PATH: model_cache}
)
def process_receipt(image_bytes: bytes):
    preprocessed = preprocess_image.local(image_bytes)
    raw = transcript_receipt.local(preprocessed)
    normalized = normalize_output.local(raw)
    return normalized
