"""MCP Server 主入口。

遵循 MCP 协议，将 RAG 知识检索、文档管理、外部工具暴露为 MCP 工具，
可被 Claude Desktop / 任意 MCP 客户端调用。

启动：
    python -m mcp_server.server
"""
import sys
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from config import config
from rag_engine.loader import DocumentLoader
from rag_engine.splitter import TextSplitter
from rag_engine.vectorstore import VectorStore
from rag_engine.retriever import HybridRetriever
from mcp_server.tools.external import web_search, current_time

# 共享实例
_vectorstore = VectorStore()
_retriever = HybridRetriever(_vectorstore)
_loader = DocumentLoader()
_splitter = TextSplitter()

mcp = FastMCP("mcp-rag-assistant")


@mcp.tool()
def search_knowledge(query: str) -> str:
    """在知识库中检索与问题相关的内容。

    Args:
        query: 用户的检索问题
    """
    docs = _retriever.retrieve(query)
    if not docs:
        return "知识库中未检索到相关内容。"
    blocks = []
    for i, d in enumerate(docs, 1):
        source = d.metadata.get("source", "未知来源")
        blocks.append(f"[{i}] 来源: {source}\n内容: {d.page_content}")
    return "\n\n".join(blocks)


@mcp.tool()
def ingest_document(file_path: str) -> str:
    """加载并入库一份文档（PDF/Markdown/docx/txt）。

    Args:
        file_path: 文档在本地的绝对路径
    """
    docs = _loader.load(file_path)
    chunks = _splitter.split(docs)
    _vectorstore.add_documents(chunks)
    _retriever.refresh_bm25()
    return f"已入库 {len(chunks)} 个片段，来源: {Path(file_path).name}。当前知识库共 {_vectorstore.count()} 个片段。"


@mcp.tool()
def list_documents() -> str:
    """列出知识库中已入库的所有文档来源。"""
    all_data = _vectorstore.get_all()
    sources = {}
    for meta in all_data.get("metadatas", []):
        if meta:
            name = meta.get("source", "未知")
            sources[name] = sources.get(name, 0) + 1
    if not sources:
        return "知识库为空。"
    lines = [f"- {name}: {cnt} 个片段" for name, cnt in sources.items()]
    return "知识库文档列表：\n" + "\n".join(lines)


@mcp.tool()
def delete_document(source: str) -> str:
    """按来源文件名删除知识库中的文档。

    Args:
        source: 文档来源名（与 list_documents 返回一致）
    """
    _vectorstore.delete_by_source(source)
    _retriever.refresh_bm25()
    return f"已删除来源为 {source} 的文档。"


@mcp.tool()
def web_search_tool(query: str) -> str:
    """联网搜索补充知识库之外的信息。

    Args:
        query: 搜索关键词
    """
    return web_search(query)


@mcp.tool()
def get_time() -> str:
    """获取当前时间。"""
    return current_time()


def main():
    print(f"[MCP-RAG] 知识库目录: {config.docs_dir}")
    print(f"[MCP-RAG] 向量库目录: {config.chroma_persist_dir}")
    print(f"[MCP-RAG] 已注册工具: search_knowledge, ingest_document, "
          f"list_documents, delete_document, web_search_tool, get_time")
    print("[MCP-RAG] 预加载 embedding 模型中（避免首次工具调用超时）...")
    from rag_engine.embedder import Embedder
    Embedder.get()  # 强制加载模型到内存
    print("[MCP-RAG] embedding 模型预加载完成")
    print("[MCP-RAG] BM25 索引将在首次检索时构建")
    mcp.run()


if __name__ == "__main__":
    main()
