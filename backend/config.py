"""Shared Modal app, images, and constants.

One Modal app holds both the HTTP gateway and the GPU functions. A Modal app is
a deployment namespace, not a resource boundary — GPU is requested per function
— so there is no reason to split them across two deployments.

Images are split, though: the gateway has no use for torch/transformers/opencv,
and pulling several GB it never imports would inflate the cold start that every
request pays for.
"""

import modal

app = modal.App("receipt-parser")

SECRET_NAME = "RECEIPT_PARSER_SECRET"

# --- Gateway: FastAPI only, deliberately tiny -------------------------------
gateway_image = modal.Image.debian_slim(python_version="3.12").pip_install_from_requirements(
    "requirements-gateway.txt"
)

# --- Inference: the full ML stack -------------------------------------------
MODEL_NAME = "naver-clova-ix/donut-base-finetuned-cord-v2"
MODEL_CACHE_PATH = "/root/models"

model_cache = modal.Volume.from_name("hf-hub-cache", create_if_missing=True)

inference_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install_from_requirements("requirements-gpu.txt")
    .env(
        {
            "HF_HUB_CACHE": MODEL_CACHE_PATH,
            "HF_HUB_ENABLE_HF_TRANSFER": "0",
        }
    )
)
