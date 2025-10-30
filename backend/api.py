# backend/web_app.py

from pathlib import Path
import fastapi
import fastapi.staticfiles
import modal

app = modal.App("receipt-parser-webapp")
web_app = fastapi.FastAPI(title="Receipt Parser Web App")

# Reference your deployed function from funcs.py
parse_receipt = modal.Function.from_name("receipt-parsing-functions", "process_receipt")

# Api endpoints to parse, get the result, and get health

@web_app.post("/parse")
async def parse(request: fastapi.Request):
    form = await request.form()
    file = await form["receipt"].read()  # 'receipt' is the <input name="receipt" /> in frontend
    call = parse_receipt.spawn(file)
    return {"call_id": call.object_id}

@web_app.get("/result/{call_id}")
async def poll_results(call_id: str):
    function_call = modal.functions.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except TimeoutError:
        return fastapi.responses.JSONResponse(content="", status_code=202)
    return result


# --------------- STATIC FRONTEND ---------------- #

# Bundle static assets (React or Next.js build output)
# Adjust path to wherever your frontend build lives:
local_assets_path = Path(__file__).parent / "frontend"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("fastapi[standard]==0.115.4")
    .add_local_dir(local_assets_path, remote_path="/assets")
)

# Serve frontend + API together
@app.function(image=image)
@modal.concurrent(max_inputs=1000)
@modal.asgi_app()
def wrapper():
    web_app.mount("/", fastapi.staticfiles.StaticFiles(directory="/assets", html=True))
    return web_app
