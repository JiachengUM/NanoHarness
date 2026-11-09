"""
复杂推理 HTTP 服务：对应 complex_reasoning_agent src/server/api.py 的全部接口。
使用 mind 的 ReAct agent + get_default_tools 作为推理引擎，不依赖 Nacos/原版 convertor。
"""
import json
import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware

from projects.mind.complex_reasoning.agent.agent import create_agent
from projects.mind.complex_reasoning.tools import get_default_tools
from projects.mind.complex_reasoning.utils.http_client import HttpClient
from projects.mind.complex_reasoning.utils.plugins.plugins import call_fc
from projects.mind.complex_reasoning.utils.plugins.question_id_pool import get_question_id_pool

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI
except ImportError:
    FastAPI = None  # type: ignore

if FastAPI is None:
    raise RuntimeError("需要安装 fastapi: pip install fastapi")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse_chunk(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(r: Request):
    """OpenAI 兼容的流式对话：用 ReAct agent 执行，SSE 返回 delta.content。"""
    try:
        body = await r.json()
        model = body.get("model", "default")
        messages = body.get("messages", [])
        chat_id = body.get("chat_id") or f"chatbox_{uuid.uuid4().hex}"
        show_json = body.get("show_json", False)

        if not messages:
            return {"errorcode": 400, "errormsg": "messages 为空"}
        # 最后一条 user 作为 query
        query = None
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                query = m["content"] if isinstance(m["content"], str) else str(m["content"])
                break
        if not query:
            return {"errorcode": 400, "errormsg": "无 user 消息"}

        tools = get_default_tools(chat_id)
        agent = create_agent(tools=tools, max_turns=5)
        trace_id = body.get("trace_id") or uuid.uuid4().hex

        async def stream():
            full_text = []
            async for step in agent.astream(query):
                if isinstance(step, str):
                    full_text.append(step)
                    if not show_json:
                        yield _sse_chunk({
                            "id": trace_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": model,
                            "choices": [{"index": 0, "delta": {"content": step}, "finish_reason": None}],
                        })
            # 结束块
            yield _sse_chunk({
                "id": trace_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            })

        return StreamingResponse(stream(), media_type="text/event-stream")
    except Exception as e:
        logger.exception("chat_completions error: %s", e)
        return {"errorcode": 500, "errormsg": str(e)}


@app.post("/v1/agent/do/stream")
async def agent_do_stream(r: Request):
    """火山 agent 流式：body 含 query、chat_id、question_id、history 等，用 ReAct agent 流式返回 SSE。"""
    try:
        body = await r.json()
        query = body.get("query", "")
        chat_id = body.get("chat_id") or f"chatbox_{uuid.uuid4().hex}"
        question_id = body.get("question_id") or uuid.uuid4().hex

        if not query:
            return {"errorcode": 400, "errormsg": "query 为空"}

        tools = get_default_tools(chat_id)
        agent = create_agent(tools=tools, max_turns=5)

        async def stream():
            async for step in agent.astream(query):
                if isinstance(step, str):
                    yield _sse_chunk({"content": step, "stage": "talk"})
            yield _sse_chunk({"rc": 2, "stage": "done"})

        return StreamingResponse(stream(), media_type="text/event-stream")
    except Exception as e:
        logger.exception("agent_do_stream error: %s", e)
        return {"errorcode": 500, "errormsg": str(e)}


@app.get("/get_question_id")
async def get_question_id():
    qid = await get_question_id_pool().get_id()
    return {"question_id": qid}


@app.get("/query_function")
async def query_function(query: str):
    chat_id = f"chatbox_{uuid.uuid4().hex}"
    fc_result = await call_fc(query, chat_id)
    return {"fc_result": fc_result}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload_vlm_result")
async def upload_vlm_result(r: Request):
    """VLM 状态上报占位：mind 侧暂无 upload_vlm_state，仅返回成功。"""
    try:
        body = await r.json()
        logger.info("upload_vlm_result: %s", body)
        return {"status": 0, "errormsg": "上传成功"}
    except Exception as e:
        logger.exception("upload_vlm_result error: %s", e)
        return {"status": 500, "errormsg": str(e)}


@app.on_event("startup")
async def startup():
    await HttpClient.get_instance()
    await get_question_id_pool().init_pool()
    logger.info("complex_api_server started")


@app.on_event("shutdown")
async def shutdown():
    client = await HttpClient.get_instance()
    await client.close()
    logger.info("complex_api_server shutdown")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
