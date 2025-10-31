import os
import fastapi
from fastapi import Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import modal

# Create Modal app
app = modal.App("receipt-parser-api")

# Create FastAPI app
web_app = fastapi.FastAPI()

# Allowed origins (frontend)
ALLOWED_ORIGINS = [
    "https://receipt-parser.vercel.app",  # production
    "http://localhost:3000",              # local dev
]

# Get API key from Modal secrets
API_KEY = os.environ.get("RECEIPT_API_KEY")
AUTH_HEADER = "authorization"
auth_header = request.headers.get(AUTH_HEADER)

if not auth_header or not auth_header.startswith("Bearer "):
    raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

key = auth_header.split("Bearer ")[-1]
if key != API_KEY:
    raise HTTPException(status_code=401, detail="Unauthorized")


# Add CORS
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add API key auth
@web_app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Skip health check
    if request.url.path == "/health":
        return await call_next(request)

    key = request.headers.get(API_KEY_HEADER)
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await call_next(request)

# Health check
@web_app.get("/health")
async def health():
    return {"status": "ok", "message": "Receipt Parser API healthy"}

# Status check (basically same as health)
@web_app.get("/status")
async def get_status():
    fn = modal.Function.from_name("receipt-parsing-functions", "get_status")
    return fn.remote()

# Main endpoint to process receipt
@web_app.post("/parse")
async def parse_receipt(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type")

    # Read bytes
    image_bytes = await file.read()

    # Get Modal function
    process_fn = modal.Function.from_name("receipt-parsing-functions", "process_receipt")

    # Call function with secret key
    result = process_fn.remote(image_bytes, api_key=API_KEY)
    return result

# Modal deployment config
image = modal.Image.debian_slim(python_version="3.12").pip_install_from_requirements(
    "requirements.txt"
)

@app.function(image=image, secrets=[modal.Secret.from_name("RECEIPT_PARSER_SECRET")])
@modal.asgi_app()
def fastapi_app():
    return web_app
