import modal
from pathlib import Path

APP_NAME = "receipt-parsing-functions"


def test_hello():
    fn = modal.Function.from_name(APP_NAME, "test_hello")
    print("Calling test_hello()...")
    result = fn.remote()
    print("✅ test_hello result:", result)


def test_square():
    fn = modal.Function.from_name(APP_NAME, "square")
    print("Calling square(5)...")
    result = fn.remote(5)
    print("✅ square result:", result)


def test_preprocess_image():
    fn = modal.Function.from_name(APP_NAME, "preprocess_image")
    print("Calling preprocess_image()...")

    file_path = Path("test_photos/image.jpg")
    if not file_path.exists():
        print("❌ test_photos/image.jpg not found")
        return

    with open(file_path, "rb") as f:
        image_bytes = f.read()

    result = fn.remote(image_bytes)
    print(f"✅ preprocess_image result: {len(result)} bytes")


def test_transcript_receipt():
    fn = modal.Function.from_name(APP_NAME, "transcript_receipt")
    print("Calling transcript_receipt()...")

    file_path = Path("test_photos/image.jpg")
    if not file_path.exists():
        print("❌ test_photos/image.jpg not found")
        return

    with open(file_path, "rb") as f:
        image_bytes = f.read()

    result = fn.remote(image_bytes)
    print("✅ transcript_receipt result:")
    print(result)

def test_donut():
    fn = modal.Function.from_name(APP_NAME, "process_receipt")
    with open("test_photos/image.jpg", "rb") as f:
        image_bytes = f.read()
    result = fn.remote(image_bytes, "4012089e-e5c3-498b-84b3-3dded81bd1c6")
    print("✅ test_donut result:")
    print(result)



if __name__ == "__main__":
    print("🚀 Running Modal function tests...\n")

    try:
        test_donut()
    except Exception as e:
        print("❌ test_hello failed:", e)    
    """try:
        test_hello()
    except Exception as e:
        print("❌ test_hello failed:", e)

    print()
    try:
        test_square()
    except Exception as e:
        print("❌ square failed:", e)

    print()
    try:
        test_preprocess_image()
    except Exception as e:
        print("❌ preprocess_image failed:", e)

    print()
    try:
        test_transcript_receipt()
    except Exception as e:
        print("❌ transcript_receipt failed:", e)

    print("\n🏁 Tests complete.")"""