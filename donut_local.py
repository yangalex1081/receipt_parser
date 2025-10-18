""" This is a function to test out if DONUT is working locally before I try and get it working on Modal """

import sys
import re
from pathlib import Path
from PIL import Image

import torch
from transformers import DonutProcessor, VisionEncoderDecoderModel


processor = DonutProcessor.from_pretrained("debu-das/donut_receipt_v1.20", use_fast=True)
model = VisionEncoderDecoderModel.from_pretrained("debu-das/donut_receipt_v1.20"
)

device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)

def process_document(image):
    # prepare encoder inputs
    pixel_values = processor(image, return_tensors="pt").pixel_values
    
    # prepare decoder inputs
    task_prompt = "<s_cord-v2>"
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
    
    return processor.token2json(sequence)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <image_file>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    # Open image and run OCR
    image = Image.open(file_path).convert("RGB")
    result = process_document(image)

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))