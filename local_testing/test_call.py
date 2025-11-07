import modal
from pathlib import Path
from dotenv import load_dotenv
import os
from PIL import Image
import io
import matplotlib.pyplot as plt

# ====================================================
# 🔧 Global Config
# ====================================================

ENV_PATH = Path("/Users/alexyang/Documents/GitHub/receipt_parser/receipt-parser-frontend/.env")
IMAGE_PATH = Path("/Users/alexyang/Documents/GitHub/receipt_parser/test_photos/image.jpg")
APP_NAME = "receipt-parsing-functions"

# Load environment variables
load_dotenv(ENV_PATH)

API_KEY = os.getenv("VITE_API_KEY")

if not API_KEY:
    raise SystemExit("❌ Missing API key. Ensure VITE_API_KEY is set in .env")

# ====================================================
# 🧠 Helper
# ====================================================
def load_image_bytes():
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"❌ Image not found at {IMAGE_PATH}")
    with open(IMAGE_PATH, "rb") as f:
        return f.read()


def display_image_comparison(original_bytes, processed_bytes, title="Preprocessing Result"):
    original = Image.open(io.BytesIO(original_bytes)).convert("RGB")
    processed = Image.open(io.BytesIO(processed_bytes)).convert("RGB")

    plt.figure(figsize=(12, 6))
    plt.subplot(1, 2, 1)
    plt.imshow(original)
    plt.title("Original")
    plt.axis("off")

    plt.subplot(1, 2, 2)
    plt.imshow(processed)
    plt.title(title)
    plt.axis("off")

    plt.tight_layout()
    plt.show()


# ====================================================
# 🧪 Tests
# ====================================================
def test_preprocess_image():
    print("🧩 Testing preprocess_image()...")
    fn = modal.Function.from_name(APP_NAME, "preprocess_image")
    img_bytes = load_image_bytes()
    result = fn.remote(img_bytes)
    print("✅ preprocess_image: success (showing preview)")
    display_image_comparison(img_bytes, result, "Preprocessed (Contrast + Denoised)")


def test_transcript_receipt():
    print("🧠 Testing transcript_receipt()...")
    fn = modal.Function.from_name(APP_NAME, "transcript_receipt")
    img_bytes = load_image_bytes()
    result = fn.remote(img_bytes, API_KEY)
    print("✅ transcript_receipt result:\n", result)


def test_normalize_output():
    print("🧹 Testing normalize_output()...")
    fn = modal.Function.from_name(APP_NAME, "normalize_output")
    mock_raw = [{'cnt': '1 x', 'price': '85,000'}, {'nm': 'Tahu Goreng', 'cnt': '2 x', 'price': '36,000'}, {'nm': 'Tempe Goreng', 'cnt': '2 x', 'price': '36,000'}, {'nm': 'Tahu Telor Asin', 'cnt': '1 x', 'price': '40,000.'}, {'nm': 'Nasi Goreng Samb', 'cnt': '1 x', 'price': '70,000'}, {'nm': 'Bbk Panggang Sam', 'cnt': '3 x', 'price': '366,000'}, {'nm': 'Ayam Sambal Hija', 'cnt': '1 x', 'price': '92,000'}, {'nm': 'Hot Tea', 'cnt': '2 x', 'price': '44,000'}, {'nm': 'Ice Kopi', 'cnt': '1 x', 'price': '32,000'}, {'nm': 'Tahu Telor Asin', 'cnt': '1 x', 'price': '40,000'}, {'nm': 'Free Ice Tea', 'cnt': '1 x', 'price': '0'}, {'nm': 'Bebek Street', 'cnt': '1 x', 'price': '44,000'}, {'nm': 'Ice Tea Tawar', 'cnt': '1 x', 'price': '18,000', 'sub_total': {'subtotal_price': '1,346,000', 'service_price': '100,950', 'tax_price': '144,695', 'etc': '-45'}, 'total': {'total_price': '1,591,600'}}]
    result = fn.remote(mock_raw)
    print("✅ normalize_output result:\n", result)


def test_get_status():
    print("⚙️ Testing get_status()...")
    fn = modal.Function.from_name(APP_NAME, "get_status")
    result = fn.remote()
    print("✅ get_status result:\n", result)


def test_process_receipt():
    print("🧾 Testing process_receipt()...")
    fn = modal.Function.from_name(APP_NAME, "process_receipt")
    img_bytes = load_image_bytes()
    result = fn.remote(img_bytes, API_KEY)
    print("✅ process_receipt result:\n", result)

def test_preprocess_and_parse():
    """
    🧠 Combined test:
    1️⃣ Preprocesses the image using preprocess_image()
    2️⃣ Calls transcript_receipt() on the processed image
    3️⃣ Displays before/after comparison
    """
    print("🔁 Testing combined preprocess + parse pipeline...")

    preprocess_fn = modal.Function.from_name(APP_NAME, "preprocess_image")
    parse_fn = modal.Function.from_name(APP_NAME, "transcript_receipt")

    img_bytes = load_image_bytes()

    # Step 1: Preprocess
    processed_bytes = preprocess_fn.remote(img_bytes)
    print("✅ preprocess_image: success")

    # Show comparison for debugging
    display_image_comparison(img_bytes, processed_bytes, title="Preprocessed for Parsing")

    # Step 2: Parse (transcribe)
    print("🧠 Calling transcript_receipt() on processed image...")
    parsed_result = parse_fn.remote(processed_bytes, API_KEY)
    print("✅ transcript_receipt result:\n", parsed_result)



# ====================================================
# 🚀 Entry Point
# ====================================================
# --- Configure which tests to run ---
RUN_GET_STATUS = True
RUN_PREPROCESS = False
RUN_TRANSCRIPT = True
RUN_NORMALIZE = False
RUN_PROCESS = False
RUN_COMBINED = False

# ------------------------------------

if __name__ == "__main__":
    print("\n🚀 Running selected Modal function tests...\n")

    if RUN_GET_STATUS:
        print("\n▶️ Running get_status...")
        try:
            test_get_status()
        except Exception as e:
            print("❌ get_status failed:", e)

    if RUN_PREPROCESS:
        print("\n▶️ Running preprocess_image...")
        try:
            test_preprocess_image()
        except Exception as e:
            print("❌ preprocess_image failed:", e)

    if RUN_TRANSCRIPT:
        print("\n▶️ Running transcript_receipt...")
        try:
            test_transcript_receipt()
        except Exception as e:
            print("❌ transcript_receipt failed:", e)

    if RUN_NORMALIZE:
        print("\n▶️ Running normalize_output...")
        try:
            test_normalize_output()
        except Exception as e:
            print("❌ normalize_output failed:", e)

    if RUN_PROCESS:
        print("\n▶️ Running process_receipt...")
        try:
            test_process_receipt()
        except Exception as e:
            print("❌ process_receipt failed:", e)

    if RUN_COMBINED:
        print("\n▶️ Running preprocess_and_parse...")
        try:
            test_preprocess_and_parse()
        except Exception as e:
            print("❌ preprocess_and_parse failed:", e)


    print("\n🏁 Tests complete.")
