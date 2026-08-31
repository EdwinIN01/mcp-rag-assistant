"""对话接口：检索 + LLM 生成，支持 SSE 流式输出。"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import services
from ..schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """非流式对话：检索知识库后生成回答，带引用来源和多轮历史记忆。"""
    history = [m.model_dump() for m in req.history]
    answer, sources, latency = await services.chat(req.message, history, req.top_k)
    return ChatResponse(answer=answer, sources=sources, latency_ms=round(latency, 1))


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """流式对话（SSE）。

    事件序列：
        event: sources  → 检索完成，引用来源 + 检索耗时
        event: delta    → 回答增量片段（多次）
        event: done     → 生成结束
    """
    history = [m.model_dump() for m in req.history]

    async def event_stream():
        docs, latency = await services.search(req.message, req.top_k)
        if not docs:
            yield _sse("sources", {"sources": [], "latency_ms": round(latency, 1)})
            yield _sse("delta", {"content": "知识库中未检索到相关内容，请先上传文档。"})
            yield _sse("done", {})
            return

        context, sources = services.build_context(docs)
        current_user_msg = (
            f"用户问题：{req.message}\n\n"
            f"参考资料（来自知识库）：\n{context}\n\n"
            f"请根据以上参考资料回答用户问题。若参考资料无法回答，请基于历史对话说明。"
        )
        messages = await services.build_messages(history, current_user_msg)

        yield _sse("sources", {"sources": sources, "latency_ms": round(latency, 1)})
        async for delta in services.stream_answer(messages):
            yield _sse("delta", {"content": delta})
        yield _sse("done", {})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
