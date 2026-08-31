"""业务服务层：同步 RAG 引擎异步化 + LLM 异步调用统一封装。

异步化策略：
- 检索链路（embedding 推理 / Chroma 查询 / BM25 / 重排）是同步阻塞的
  CPU 密集操作，用 asyncio.to_thread 丢到线程池，避免卡死事件循环；
- LLM 调用改为 AsyncOpenAI，天然异步，支持流式；
- 对话历史压缩逻辑与 web_ui 保持一致（最近 3 轮原文 + 更早摘要）。
"""
import asyncio
import re
import time
from typing import AsyncIterator, Optional

from langchain_core.documents import Document
from openai import AsyncOpenAI

from config import config
from .deps import get_retriever
from .observability import get_logger, start_observation

log = get_logger("services")

SYSTEM_PROMPT = (
    "你是一个基于知识库的问答助手。严格遵守以下规则：\n"
    "1. 只能基于用户提供的参考资料回答，不得使用资料之外的知识。\n"
    "2. 在引用处标注 [1] [2] 等编号，确保每个论断都有出处。\n"
    "3. 若参考资料无法回答，明确说明'根据现有资料无法回答'，不得编造。\n"
    "4. 不得对检索内容做超出原文含义的推断或扩展。"
)

RECENT_N = 6  # 保留最近 3 轮（6 条消息）原文，更早的压缩为摘要

_llm_client: Optional[AsyncOpenAI] = None


def get_llm() -> Optional[AsyncOpenAI]:
    """AsyncOpenAI 客户端单例（复用连接池）。未配置 Key 返回 None。"""
    global _llm_client
    if not config.llm_api_key:
        return None
    if _llm_client is None:
        _llm_client = AsyncOpenAI(
            base_url=config.llm_api_base, api_key=config.llm_api_key
        )
    return _llm_client


# ---------- 检索（同步引擎异步化） ----------
async def search(query: str, top_k: Optional[int] = None) -> tuple[list[Document], float]:
    """线程池中执行阻塞检索（含缓存短路），返回 (文档列表, 耗时ms)。"""
    retriever = get_retriever()
    t0 = time.perf_counter()
    with start_observation(
        "retrieval", as_type="retriever", input={"query": query, "top_k": top_k}
    ) as obs:
        docs = await asyncio.to_thread(retriever.retrieve, query, top_k)
        latency = (time.perf_counter() - t0) * 1000
        obs.update(
            output=[
                {"source": d.metadata.get("source", "未知"), "content": d.page_content[:200]}
                for d in docs
            ],
            metadata={
                "latency_ms": round(latency, 1),
                "results": len(docs),
                "cache_hit": retriever.last_cache_hit,
            },
        )
    log.info(
        "retrieval_done",
        query=query,
        results=len(docs),
        latency_ms=round(latency, 1),
        cache_hit=retriever.last_cache_hit,
        sources=[d.metadata.get("source") for d in docs],
    )
    return docs, latency


async def search_with_details(query: str) -> tuple[dict, float]:
    """线程池中执行检索并返回四阶段过程详情（向量/BM25/RRF/重排）。"""
    retriever = get_retriever()
    t0 = time.perf_counter()
    with start_observation(
        "retrieval_details", as_type="retriever", input={"query": query}
    ) as obs:
        details = await asyncio.to_thread(retriever.retrieve_with_details, query)
        latency = (time.perf_counter() - t0) * 1000
        obs.update(metadata={"latency_ms": round(latency, 1)})
    log.info("retrieval_details_done", query=query, latency_ms=round(latency, 1))
    return details, latency


# ---------- 对话 ----------
def _extract_context(user_msg: str) -> str:
    """从拼装的 user 消息中提取参考资料原文（无 Key 降级展示用）。"""
    m = re.search(r"参考资料[^\n]*\n(.*?)(?:\n\n请根据|请根据)", user_msg, re.S)
    return m.group(1).strip() if m and m.group(1).strip() else user_msg


def build_context(docs: list[Document]) -> tuple[str, list[str]]:
    """把检索结果拼装为带编号的参考资料 + 引用来源列表。"""
    context = "\n\n".join(f"[{i + 1}] {d.page_content}" for i, d in enumerate(docs))
    sources = [d.metadata.get("source", "未知") for d in docs]
    return context, sources


async def _summarize_history(old_msgs: list[dict]) -> str:
    """用 LLM 将旧对话压缩成摘要。无 Key 或失败时降级为截断。"""
    dialogue = "\n".join(
        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
        for m in old_msgs
        if m.get("role") in ("user", "assistant")
    )
    if not dialogue:
        return ""
    client = get_llm()
    if client is None:
        return dialogue[:500]
    try:
        resp = await client.chat.completions.create(
            model=config.llm_model,
            messages=[
                {"role": "system", "content":
                    "请将以下对话历史压缩成一段简洁的摘要，保留关键信息和上下文，不超过200字。"},
                {"role": "user", "content": dialogue},
            ],
            temperature=0.0,
        )
        return resp.choices[0].message.content
    except Exception:
        return dialogue[:500]


async def build_messages(history: list[dict], current_user_msg: str) -> list[dict]:
    """构建带历史记忆的 messages：超过阈值时旧对话摘要压缩，最近轮次保留原文。"""
    history = [m for m in history if m.get("role") in ("user", "assistant")]

    if len(history) > RECENT_N:
        old_msgs, recent = history[:-RECENT_N], history[-RECENT_N:]
        summary = await _summarize_history(old_msgs)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"之前对话摘要：\n{summary}"},
        ]
        messages += [{"role": m["role"], "content": m["content"]} for m in recent]
    else:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]

    messages.append({"role": "user", "content": current_user_msg})
    return messages


def _usage_details(resp) -> dict | None:
    """从 OpenAI 兼容响应中提取 token 用量（Langfuse usage_details 格式）。"""
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    return {
        "input": getattr(usage, "prompt_tokens", 0),
        "output": getattr(usage, "completion_tokens", 0),
        "total": getattr(usage, "total_tokens", 0),
    }


async def generate_answer(messages: list[dict]) -> str:
    """调用 LLM 生成回答。无 API Key 时降级返回检索片段。"""
    client = get_llm()
    fallback = (
        f"（未配置 LLM API Key，以下为检索到的参考内容）\n\n"
        f"{_extract_context(messages[-1]['content'])[:800]}"
    )
    if client is None:
        return fallback
    t0 = time.perf_counter()
    with start_observation(
        "generation",
        as_type="generation",
        input={"messages_count": len(messages), "last_message": messages[-1]["content"][:500]},
        model=config.llm_model,
        model_parameters={"temperature": 0.1},
    ) as obs:
        try:
            resp = await client.chat.completions.create(
                model=config.llm_model,
                messages=messages,
                temperature=0.1,
            )
        except Exception as e:
            obs.update(level="ERROR", status_message=f"LLM 调用失败: {e}")
            log.warning("generation_failed", error=str(e), model=config.llm_model)
            return f"（LLM 调用失败: {e}）\n\n参考内容:\n{_extract_context(messages[-1]['content'])[:800]}"
        answer = resp.choices[0].message.content
        usage = _usage_details(resp)
        latency = (time.perf_counter() - t0) * 1000
        obs.update(output=answer, usage_details=usage, metadata={"latency_ms": round(latency, 1)})
    log.info(
        "generation_done",
        model=config.llm_model,
        latency_ms=round(latency, 1),
        answer_chars=len(answer),
        **({"token_usage": usage} if usage else {}),
    )
    return answer


async def stream_answer(messages: list[dict]) -> AsyncIterator[str]:
    """流式生成回答（SSE 数据源）。无 Key 或失败时降级为一次性输出检索片段。"""
    client = get_llm()
    if client is None:
        yield (
            f"（未配置 LLM API Key，以下为检索到的参考内容）\n\n"
            f"{_extract_context(messages[-1]['content'])[:800]}"
        )
        return
    t0 = time.perf_counter()
    chunks: list[str] = []
    with start_observation(
        "generation_stream",
        as_type="generation",
        input={"messages_count": len(messages), "last_message": messages[-1]["content"][:500]},
        model=config.llm_model,
        model_parameters={"temperature": 0.1, "stream": True},
    ) as obs:
        try:
            stream = await client.chat.completions.create(
                model=config.llm_model,
                messages=messages,
                temperature=0.1,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    chunks.append(delta)
                    yield delta
        except Exception as e:
            obs.update(level="ERROR", status_message=f"LLM 流式调用失败: {e}")
            log.warning("generation_stream_failed", error=str(e), model=config.llm_model)
            yield f"（LLM 调用失败: {e}）"
            return
        obs.update(output="".join(chunks), metadata={"latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
    log.info(
        "generation_stream_done",
        model=config.llm_model,
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        answer_chars=sum(len(c) for c in chunks),
    )


async def chat(
    message: str, history: list[dict], top_k: Optional[int] = None
) -> tuple[str, list[str], float]:
    """检索 + 生成完整链路（Langfuse trace 根节点）。返回 (回答, 引用来源, 检索耗时ms)。"""
    with start_observation(
        "chat", as_type="chain", input={"message": message, "history_turns": len(history) // 2}
    ) as obs:
        t0 = time.perf_counter()
        docs, latency = await search(message, top_k)
        if not docs:
            obs.update(output="知识库中未检索到相关内容")
            return "知识库中未检索到相关内容，请先上传文档。", [], latency

        context, sources = build_context(docs)
        current_user_msg = (
            f"用户问题：{message}\n\n"
            f"参考资料（来自知识库）：\n{context}\n\n"
            f"请根据以上参考资料回答用户问题。若参考资料无法回答，请基于历史对话说明。"
        )
        messages = await build_messages(history, current_user_msg)
        answer = await generate_answer(messages)
        obs.update(
            output=answer,
            metadata={
                "sources": sources,
                "retrieval_latency_ms": round(latency, 1),
                "total_latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            },
        )
    log.info(
        "chat_done",
        message=message[:100],
        sources=sources,
        total_latency_ms=round((time.perf_counter() - t0) * 1000, 1),
    )
    return answer, sources, latency
