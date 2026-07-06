"""Streamlit 可视化前端：检索过程可视化 + 多轮对话 + 文档管理。

启动：
    streamlit run web_ui/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from config import config
from rag_engine.loader import DocumentLoader
from rag_engine.splitter import TextSplitter
from rag_engine.vectorstore import VectorStore
from rag_engine.retriever import HybridRetriever

# ---------- 初始化（缓存到 session_state） ----------
if "vectorstore" not in st.session_state:
    st.session_state.vectorstore = VectorStore()
if "retriever" not in st.session_state:
    st.session_state.retriever = HybridRetriever(st.session_state.vectorstore)
if "history" not in st.session_state:
    st.session_state.history = []

retriever = st.session_state.retriever
vectorstore = st.session_state.vectorstore


def _generate_answer(messages: list) -> str:
    """调用 LLM 生成回答。无 API Key 时降级返回检索片段。"""
    def _extract_context():
        user_msg = messages[-1]["content"] if messages else ""
        import re
        m = re.search(r"参考资料[^\n]*\n(.*?)(?:\n\n请根据|请根据)", user_msg, re.S)
        return m.group(1).strip() if m and m.group(1).strip() else user_msg

    if not config.llm_api_key:
        return f"（未配置 LLM API Key，以下为检索到的参考内容）\n\n{_extract_context()[:800]}"
    try:
        from openai import OpenAI
        client = OpenAI(base_url=config.llm_api_base, api_key=config.llm_api_key)
        resp = client.chat.completions.create(
            model=config.llm_model,
            messages=messages,
            temperature=0.3,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"（LLM 调用失败: {e}）\n\n参考内容:\n{_extract_context()[:800]}"


st.set_page_config(page_title="MCP-RAG 智能知识库助手", page_icon="📚", layout="wide")
st.title("📚 MCP-RAG 智能知识库助手")
st.caption("MCP 协议 · 混合检索 · RRF 融合 · 重排 · 检索过程可视化")

# ---------- 侧边栏：文档管理 ----------
with st.sidebar:
    st.header("📁 文档管理")

    uploaded = st.file_uploader(
        "上传文档入库", type=["pdf", "md", "txt", "docx"], accept_multiple_files=True
    )
    if uploaded and st.button("入库", type="primary"):
        loader = DocumentLoader()
        splitter = TextSplitter()
        total = 0
        for f in uploaded:
            tmp = config.docs_dir / f.name
            tmp.write_bytes(f.getbuffer())
            docs = loader.load(tmp)
            chunks = splitter.split(docs)
            vectorstore.add_documents(chunks)
            total += len(chunks)
            st.success(f"✅ {f.name}: {len(chunks)} 个片段")
        retriever.refresh_bm25()
        st.info(f"本次共入库 {total} 个片段，知识库共 {vectorstore.count()} 个片段")

    # 一键加载示例文档（data/docs 目录）
    if st.button("📚 加载示例文档入库"):
        loader = DocumentLoader()
        splitter = TextSplitter()
        docs = loader.load_dir(config.docs_dir)
        chunks = splitter.split(docs)
        vectorstore.add_documents(chunks)
        retriever.refresh_bm25()
        st.success(f"✅ 已加载 {len(docs)} 个示例文档，{len(chunks)} 个片段入库")
        st.info(f"知识库共 {vectorstore.count()} 个片段")

    st.divider()
    st.subheader("已入库文档")
    all_data = vectorstore.get_all()
    sources = {}
    for meta in all_data.get("metadatas", []):
        if meta:
            name = meta.get("source", "未知")
            sources[name] = sources.get(name, 0) + 1
    if sources:
        for name, cnt in sources.items():
            cols = st.columns([4, 1])
            cols[0].write(f"📄 {name} ({cnt})")
            if cols[1].button("删除", key=f"del_{name}"):
                vectorstore.delete_by_source(name)
                retriever.refresh_bm25()
                st.rerun()
    else:
        st.write("（知识库为空，请上传文档）")

    st.divider()
    st.subheader("检索参数")
    top_k = st.slider("向量/BM25 召回数", 3, 15, config.top_k)
    rerank_k = st.slider("重排后返回数", 1, 10, config.rerank_top_k)
    config.top_k = top_k
    config.rerank_top_k = rerank_k

# ---------- 主区域：检索 + 对话 ----------
tab_search, tab_chat = st.tabs(["🔍 检索过程可视化", "💬 多轮对话"])

# ===== 检索可视化 =====
with tab_search:
    query = st.text_input("输入检索问题", placeholder="例如：RAG 的检索优化策略有哪些？")
    if st.button("检索", type="primary") and query.strip():
        with st.spinner("检索中..."):
            details = retriever.retrieve_with_details(query)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("① 向量检索结果")
            for i, (doc, score) in enumerate(details["vector_results"], 1):
                with st.expander(f"Top{i} · 相似度 {score:.4f} · {doc.metadata.get('source', '')}"):
                    st.write(doc.page_content[:300])

            st.subheader("② BM25 关键词检索结果")
            for i, (doc, score) in enumerate(details["bm25_results"], 1):
                with st.expander(f"Top{i} · BM25分 {score:.4f} · {doc.metadata.get('source', '')}"):
                    st.write(doc.page_content[:300])

        with col2:
            st.subheader("③ RRF 融合结果")
            for i, (doc, score) in enumerate(details["fused_results"][:config.top_k], 1):
                with st.expander(f"Top{i} · RRF分 {score:.4f} · {doc.metadata.get('source', '')}"):
                    st.write(doc.page_content[:300])

            st.subheader("④ 重排后最终结果")
            for i, doc in enumerate(details["reranked"], 1):
                st.markdown(f"**Top{i}** · `{doc.metadata.get('source', '')}`")
                st.info(doc.page_content[:400])

        st.divider()
        cache_stats = retriever.cache.stats()
        st.caption(f"缓存状态：精确缓存 {cache_stats['exact_size']} 条 · 语义索引 {cache_stats['semantic_size']} 条")

# ===== 多轮对话 =====
with tab_chat:
    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📎 引用来源"):
                    for s in msg["sources"]:
                        st.write(f"- {s}")

    user_input = st.chat_input("提问（将自动检索知识库）")
    if user_input:
        st.session_state.history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("检索 + 生成中..."):
                docs = retriever.retrieve(user_input)
                if not docs:
                    answer = "知识库中未检索到相关内容，请先上传文档。"
                    sources = []
                else:
                    context = "\n\n".join(
                        [f"[{i+1}] {d.page_content}" for i, d in enumerate(docs)]
                    )
                    sources = [d.metadata.get("source", "未知") for d in docs]

                    # 构建带历史记忆的 messages
                    system_prompt = (
                        "你是一个基于知识库的问答助手。请根据用户提供的参考资料回答问题，"
                        "并在引用处标注 [1] [2] 等编号。若参考资料无法回答，可基于历史对话回复。"
                    )
                    current_user_msg = (
                        f"用户问题：{user_input}\n\n"
                        f"参考资料（来自知识库）：\n{context}\n\n"
                        f"请根据以上参考资料回答用户问题。若参考资料无法回答，请基于历史对话说明。"
                    )
                    messages = [{"role": "system", "content": system_prompt}]
                    # history 最后一条是刚添加的当前 user 消息，只取之前的作为历史
                    for msg in st.session_state.history[:-1]:
                        if msg["role"] in ("user", "assistant"):
                            messages.append({"role": msg["role"], "content": msg["content"]})
                    messages.append({"role": "user", "content": current_user_msg})

                    answer = _generate_answer(messages)
            st.markdown(answer)
            if sources:
                with st.expander("📎 引用来源"):
                    for s in sources:
                        st.write(f"- {s}")

        st.session_state.history.append(
            {"role": "assistant", "content": answer, "sources": sources}
        )
        st.rerun()
