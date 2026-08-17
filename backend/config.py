"""Shared Modal app, images, and constants.

One Modal app holds both the HTTP gateway and the GPU functions. A Modal app is
a deployment namespace, not a resource boundary — GPU is requested per function
— so there is no reason to split them across two deployments.

Images are split, though: the gateway has no use for torch/transformers/opencv,
and pulling several GB it never imports would inflate the cold start that every
request pays for.
"""

from pathlib import Path

import modal

app = modal.App("receipt-parser")

SECRET_NAME = "RECEIPT_PARSER_SECRET"

# Requirements paths are resolved against this file, not the working directory,
# so `modal deploy` works from the repo root or from backend/.
_HERE = Path(__file__).parent

# Modal only ships the entrypoint file to containers; sibling modules must be
# added explicitly or the container dies with ModuleNotFoundError on import.
LOCAL_SOURCES = ("config", "funcs", "gateway")

# --- Gateway: FastAPI only, deliberately tiny -------------------------------
gateway_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(_HERE / "requirements-gateway.txt"))
    .add_local_python_source(*LOCAL_SOURCES)
)

# --- Inference: the full ML stack -------------------------------------------
MODEL_NAME = "naver-clova-ix/donut-base-finetuned-cord-v2"
MODEL_CACHE_PATH = "/root/models"

model_cache = modal.Volume.from_name("hf-hub-cache", create_if_missing=True)

inference_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install_from_requirements(str(_HERE / "requirements-gpu.txt"))
    .env(
        {
            "HF_HUB_CACHE": MODEL_CACHE_PATH,
            "HF_HUB_ENABLE_HF_TRANSFER": "0",
        }
    )
    .add_local_python_source(*LOCAL_SOURCES)
)
