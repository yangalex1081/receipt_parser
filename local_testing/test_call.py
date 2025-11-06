import modal
from pathlib import Path
from PIL import Image
import io
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os

# ==============================
# Global Config
# ==============================

# Path to your .env file
ENV_PATH = Path("/Users/alexyang/Documents/GitHub/receipt_parser/receipt-parser-frontend/.env")

# Load environment variables from that file
load_dotenv(ENV_PATH)

APP_NAME = "receipt-parsing-functions"
API_KEY = os.getenv("VITE_API_KEY")  # Key name from .env file
IMAGE_PATH = Path("/Users/alexyang/Documents/GitHub/receipt_parser/test_photos/image.jpg")

# ==============================
# Helper Functions
# ==============================
def load_image_bytes():
    """Read image bytes from the global path."""
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"❌ Image not found: {IMAGE_PATH}")
    with open(IMAGE_PATH, "rb") as f:
        return f.read()

# ==============================
# Tests
# ==============================
def test_donut():
    fn = modal.Function.from_name(APP_NAME, "process_receipt")
    print("Calling process_receipt()...")

    if not API_KEY:
        raise ValueError("❌ Missing API key. Make sure .env contains VITE_API_KEY")

    image_bytes = load_image_bytes()
    result = fn.remote(image_bytes, API_KEY)
    print("✅ process_receipt result:\n", result)


# ==============================
# Entry Point
# ==============================
if __name__ == "__main__":
    print("🚀 Running Modal function tests...\n")

    try:
        test_donut()
    except Exception as e:
        print("❌ test_donut failed:", e)

    print("\n🏁 Tests complete.")
