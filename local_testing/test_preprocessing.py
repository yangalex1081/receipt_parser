import io
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import matplotlib.pyplot as plt

def preprocess_image_1(image_bytes: bytes) -> bytes:
    """
    Preprocess receipt images:
      - Converts to grayscale
      - Auto-enhances contrast
      - Light denoising
      - Resizes carefully
      - Returns RGB bytes for Donut
    """

    # Load image and convert to grayscale
    image = Image.open(io.BytesIO(image_bytes)).convert("L")
    img_np = np.array(image)

    # --- Step 1: Adaptive histogram equalization (CLAHE) for smart contrast ---
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    img_np = clahe.apply(img_np)

    # --- Step 2: Light denoising ---
    img_np = cv2.fastNlMeansDenoising(img_np, None, 10, 7, 21)

    # --- Step 3: Resize carefully ---
    max_side = 1365
    h, w = img_np.shape
    scale = min(max_side / max(w, h), 1.0)  # never upscale
    if scale < 1.0:
        img_np = cv2.resize(img_np, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # --- Step 4: Convert back to RGB for Donut ---
    image = Image.fromarray(img_np).convert("RGB")

    # --- Step 5: Optional sharpening for clarity ---
    image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=1))

    # --- Step 6: Save to bytes ---
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()

def preprocess_image_2(image_bytes: bytes) -> bytes:
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



def compare_images(path):
    with open(path, "rb") as f:
        original_bytes = f.read()

    processed_bytes = preprocess_image_2(original_bytes)

    # Convert both for display
    original = Image.open(io.BytesIO(original_bytes)).convert("RGB")
    processed = Image.open(io.BytesIO(processed_bytes)).convert("RGB")

    # Display side-by-side
    plt.figure(figsize=(12, 6))
    plt.subplot(1, 2, 1)
    plt.imshow(original)
    plt.title("Original")
    plt.axis("off")

    plt.subplot(1, 2, 2)
    plt.imshow(processed)
    plt.title("Preprocessed (No Rotation, Stronger Contrast)")
    plt.axis("off")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    image_path = input("Enter path to your receipt image: ").strip()
    compare_images(image_path)
