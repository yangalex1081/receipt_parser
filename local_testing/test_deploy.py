import modal
from PIL import Image, ImageEnhance
import io
import torch
from transformers import DonutProcessor, VisionEncoderDecoderModel
import re

app = modal.App("example-get-started")


inference_image = modal.Image.debian_slim(python_version="3.12").pip_install_from_requirements(
    'requirements.txt'
)


# Declare the model name, no need to add a revision so HuggingFace always gives the latest model
MODEL_NAME = "debu-das/donut_receipt_v1.20"

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
    {"HF_HUB_CACHE": MODEL_CACHE_PATH, "HF_HUB_ENABLE_HF_TRANSFER": "1"}
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

# Func 2 to read receipt using Donut
@app.function(
    image=inference_image, 
    gpu="any",
    retries=3,
    volumes={MODEL_CACHE_PATH: model_cache}
)
def transcript_receipt(image_bytes: bytes)-> dict:
    """
    Uses Donut to read through receipt bytes and return structured JSON data
    """

    # Load the bytes into a PIL image
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Get the processor and model from the setup() function
    processor, model, device = setup()

    # prepare encoder inputs
    pixel_values = processor(image, return_tensors="pt").pixel_values

    # Prep the prompt
    task_prompt = "<s_cord-v2>" #CORD (Consolidated Receipt Dataset)
    decoder_input_ids = processor.tokenizer(task_prompt, add_special_tokens=False, return_tensors="pt").input_ids

    # generate answer
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

    # postprocess
    sequence = processor.batch_decode(outputs.sequences)[0]
    sequence = sequence.replace(processor.tokenizer.eos_token, "").replace(processor.tokenizer.pad_token, "")
    sequence = re.sub(r"<.*?>", "", sequence, count=1).strip()  # remove first task start token
        
    # Convert to JSON
    output_json = processor.token2json(sequence)

    return output_json


@app.function(image = inference_image)
def test_square(x: int):
    return x ** 2

@app.function(image = inference_image)
def test_hello():
    print("hello world")
    return

@app.function(image = inference_image)
def square(x):
    print("This code is running on a remote worker!")
    return x**2

