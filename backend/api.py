import fastapi
import modal
from fastapi.middleware.cors import CORSMiddleware

app = modal.App("receipt-parser-api")
web_app = fastapi.FastAPI(title="Receipt Parser API")

# Allow calls from Vercel domain
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["https://receipt-parser.vercel.app"]
    allow_methods=["*"],
    allow_headers=["*"],
)

parse_receipt = modal.Function.from_name("receipt-parsing-functions", "process_receipt")

@web_app.post("/parse")
async def parse(request: fastapi.Request):
    """
    Function to queue receipt to parse
    """
    form = await request.form()
    file = await form["receipt"].read()
    call = parse_receipt.spawn(file)
    return {"call_id": call.object_id}

@web_app.get("/result/{call_id}")
async def poll_results(call_id: str):
    """
    Function to poll modal to see if receipt has finished parsing
    """
    function_call = modal.functions.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except TimeoutError:
        return fastapi.responses.JSONResponse(content="", status_code=202)
    return result

@web_app.get("/health")
async def health():
    return {"status": "ok"}

@app.function()
@modal.asgi_app()
def fastapi_app():
    return web_app
