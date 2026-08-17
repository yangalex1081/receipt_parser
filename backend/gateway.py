"""HTTP gateway.

Deploy target for the whole project:

    modal deploy backend/gateway.py

Importing funcs registers the GPU functions on the same Modal app, so one
deploy covers both. Runs on the slim gateway_image — the ML stack is never
imported here (see the inference_image.imports() block in funcs.py).
"""

import os

import fastapi
import jwt
import modal
from fastapi import Depends, Header, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from config import SECRET_NAME, app, gateway_image
from funcs import process_receipt

web_app = fastapi.FastAPI()

# The browser calls /api/* on the Netlify site, which proxies here — it never
# reaches this origin directly. CORS is kept only as a second line of defence.
ALLOWED_ORIGINS = [
    "https://alexs-receipt-parser.netlify.app",  # production
    "http://localhost:3000",              # local dev
]

# Shared with Netlify: Netlify signs every proxied request with this, and we
# verify it here. The value never reaches the browser.
NETLIFY_SIGN_SECRET = os.environ.get("NETLIFY_SIGN_SECRET")

MAX_UPLOAD_BYTES = 6 * 1024 * 1024

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_netlify_signature(x_nf_sign: str = Header(default=None)):
    """Reject anything that did not arrive through our Netlify proxy.

    Netlify signs proxied requests with HS256 using NETLIFY_SIGN_SECRET. This is
    a dependency rather than an HTTP middleware on purpose: HTTPException raised
    inside a middleware bypasses FastAPI's handlers and surfaces as a 500.
    """
    if not NETLIFY_SIGN_SECRET:
        raise HTTPException(status_code=500, detail="Server missing NETLIFY_SIGN_SECRET")

    if not x_nf_sign:
        raise HTTPException(status_code=401, detail="Missing x-nf-sign header")

    try:
        claims = jwt.decode(x_nf_sign, NETLIFY_SIGN_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Signature expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid signature")

    if claims.get("iss") != "netlify":
        raise HTTPException(status_code=401, detail="Unexpected issuer")

    return claims


# Health check — unauthenticated so it stays usable as a plain uptime probe.
# Answered by this process, so it costs nothing and starts no container.
@web_app.get("/health")
async def health():
    return {"status": "ok", "message": "Receipt Parser API healthy"}


# Kick off a parse. Returns immediately with a call id — the GPU job can take
# ~65s from cold, far longer than the proxy will hold a connection.
@web_app.post("/parse")
async def parse_receipt(
    file: UploadFile = File(...),
    _claims: dict = Depends(verify_netlify_signature),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type")

    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")

    call = process_receipt.spawn(image_bytes)
    return {"status": "pending", "call_id": call.object_id}


# Poll for a spawned job. Results are retained by Modal for 7 days.
@web_app.get("/result/{call_id}")
async def get_result(
    call_id: str,
    _claims: dict = Depends(verify_netlify_signature),
):
    function_call = modal.FunctionCall.from_id(call_id)

    try:
        result = function_call.get(timeout=0)
    except TimeoutError:
        return {"status": "pending", "call_id": call_id}
    except modal.exception.OutputExpiredError:
        raise HTTPException(status_code=410, detail="Result expired")
    except Exception as exc:
        # The GPU job itself failed — surface it rather than polling forever.
        raise HTTPException(status_code=500, detail=f"Parse failed: {exc}")

    return {"status": "done", "call_id": call_id, "result": result}


@app.function(image=gateway_image, secrets=[modal.Secret.from_name(SECRET_NAME)])
@modal.asgi_app()
def fastapi_app():
    return web_app
