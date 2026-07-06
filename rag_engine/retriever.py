"""混合检索器：向量检索 + BM25 关键词检索 + RRF 融合 + 重排 + 缓存。"""
from typing import List

from langchain_core.documents import Document

from config import config
from .vectorstore import VectorStore
from .cache import QueryCache


class HybridRetriever:
    """
    混合检索流程：
        query → 缓存命中检查
              → 向量检索 + BM25 检索
              → RRF 融合排序
              → Cross-Encoder 重排
              → 写入缓存
              → 返回 Top-K
    """

    def __init__(self, vectorstore: VectorStore | None = None):
        self.vectorstore = vectorstore or VectorStore()
        self.cache = QueryCache()
        self._bm25 = None
        self._bm25_docs: List[Document] = []
        self._bm25_built = False
        self._reranker = None

    # ---------- BM25 索引 ----------
    def _build_bm25(self, documents: List[Document]):
        from rank_bm25 import BM25Okapi
        import jieba

        self._bm25_docs = documents
        tokenized = [list(jieba.cut(d.page_content)) for d in documents]
        self._bm25 = BM25Okapi(tokenized)

    def _bm25_search(self, query: str, k: int) -> List[tuple[Document, float]]:
        import jieba

        if self._bm25 is None:
            return []
        tokens = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokens)
        top_idx = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [(self._bm25_docs[i], float(scores[i])) for i in top_idx]

    # ---------- RRF 融合 ----------
    @staticmethod
    def _rrf_fuse(
        vec_results: List[tuple[Document, float]],
        bm25_results: List[tuple[Document, float]],
        k: int = 60,
    ) -> List[tuple[Document, float]]:
        """Reciprocal Rank Fusion：按排名倒数加权融合两路结果。"""
        scores: dict[str, float] = {}
        docs: dict[str, Document] = {}

        for rank, (doc, _) in enumerate(vec_results):
            key = doc.page_content
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            docs[key] = doc
        for rank, (doc, _) in enumerate(bm25_results):
            key = doc.page_content
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            docs[key] = doc

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [(docs[k], v) for k, v in ranked]

    # ---------- 重排 ----------
    def _rerank(self, query: str, documents: List[Document], top_k: int) -> List[Document]:
        if not documents:
            return []
        if self._reranker is None:
            self._reranker = self._load_reranker()
        if self._reranker is None:
            return documents[:top_k]

        pairs = [[query, d.page_content] for d in documents]
        scores = self._reranker.predict(pairs)
        # CrossEncoder.predict 返回 numpy 数组，统一转 list
        scores = list(scores)
        ranked = sorted(zip(documents, scores), key=lambda x: -float(x[1]))
        return [d for d, _ in ranked[:top_k]]

    @staticmethod
    def _load_reranker():
        model = config.reranker_model
        if not model or model.lower() in ("", "none", "null"):
            print("[Reranker] 未配置重排模型，跳过重排（向量+BM25+RRF 结果直接返回）")
            return None
        # 强制离线
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            # 先解析本地缓存路径，传绝对路径给 CrossEncoder，避免联网检查 revision
            from huggingface_hub import snapshot_download
            local_path = snapshot_download(model, local_files_only=True)
            from sentence_transformers import CrossEncoder
            print(f"[Reranker] 加载重排模型: {model}")
            return CrossEncoder(local_path)
        except Exception as e:
            print(f"[Reranker] 重排模型加载失败，将跳过重排: {e}")
            return None

    # ---------- 主检索入口 ----------
    def _ensure_bm25(self):
        """延迟构建 BM25 索引，避免页面冷启动时加载模型。"""
        if not self._bm25_built:
            self.refresh_bm25()
            self._bm25_built = True

    def retrieve(self, query: str, k: int = None) -> List[Document]:
        k = k or config.rerank_top_k

        # 1. 缓存命中
        cached = self.cache.get(query)
        if cached is not None:
            return cached

        # 2. 延迟构建 BM25
        self._ensure_bm25()

        # 3. 向量检索
        vec_results = self.vectorstore.similarity_search_with_score(
            query, k=config.top_k
        )
        vec_results = [(d, float(s)) for d, s in vec_results]

        # 4. BM25 检索
        bm25_results = self._bm25_search(query, k=config.top_k)

        # 5. RRF 融合
        fused = self._rrf_fuse(vec_results, bm25_results)
        fused_docs = [d for d, _ in fused]

        # 6. 重排
        reranked = self._rerank(query, fused_docs, top_k=k)

        # 7. 写缓存
        self.cache.set(query, reranked)
        return reranked

    def retrieve_with_details(self, query: str, k: int = None):
        """返回检索过程详情，供可视化前端展示。"""
        k = k or config.rerank_top_k
        vec_results = self.vectorstore.similarity_search_with_score(
            query, k=config.top_k
        )
        vec_results = [(d, float(s)) for d, s in vec_results]
        bm25_results = self._bm25_search(query, k=config.top_k)
        fused = self._rrf_fuse(vec_results, bm25_results)
        fused_docs = [d for d, _ in fused]
        reranked = self._rerank(query, fused_docs, top_k=k)
        return {
            "vector_results": vec_results,
            "bm25_results": bm25_results,
            "fused_results": fused,
            "reranked": reranked,
        }

    def refresh_bm25(self):
        """文档更新后重建 BM25 索引。"""
        all_data = self.vectorstore.get_all()
        documents = []
        for text, meta in zip(all_data.get("documents", []), all_data.get("metadatas", [])):
            documents.append(Document(page_content=text, metadata=meta or {}))
        if documents:
            self._build_bm25(documents)
