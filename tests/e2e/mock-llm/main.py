"""Mock LLM server for E2E tests.

Serves minimal OpenAI-compatible endpoints so the Dryade backend can function
in CI without a real LLM endpoint. Returns canned responses deterministically.
"""

import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Mock LLM Server")

_MODEL_ID = "mock-llm-1"

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": _MODEL_ID,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "mock",
            }
        ],
    }

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = _MODEL_ID
    messages: list[ChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    last_user_msg = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        "Hello",
    )
    reply = f"Mock response to: {last_user_msg[:80]}"

    if request.stream:
        # Return a non-streaming response even if stream=True for simplicity
        pass

    return JSONResponse(
        {
            "id": f"chatcmpl-mock-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model or _MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": len(reply.split()),
                "total_tokens": 10 + len(reply.split()),
            },
        }
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
