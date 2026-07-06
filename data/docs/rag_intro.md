# RAG 检索增强生成技术介绍

## 什么是 RAG

RAG（Retrieval-Augmented Generation，检索增强生成）是一种将外部知识检索与大语言模型生成相结合的技术架构。它通过在生成回答前，先从外部知识库中检索相关文档片段，再将其作为上下文提供给大模型，从而显著提升回答的准确性与可解释性，缓解大模型幻觉问题。

## RAG 核心流程

1. 文档加载：支持 PDF、Markdown、Word 等多格式文档解析。
2. 文档切分：采用递归字符切分，保留语义连贯性，通常 chunk_size 设置为 500-1000 字符，overlap 设置为 50-200。
3. 向量化：使用 Embedding 模型（如 BGE、text-embedding）将文本转为稠密向量。
4. 向量入库：存入 Chroma、FAISS、Milvus 等向量数据库。
5. 检索：用户提问后，将问题向量化，在向量库中做相似度检索。
6. 生成：将检索到的片段作为上下文，交由大模型生成最终回答。

## 检索优化策略

- 多查询生成（Multi-Query）：用 LLM 将原问题改写为多个子问题，分别检索后合并，提升召回率。
- HyDE（Hypothetical Document Embedding）：先让 LLM 生成假设性答案，再用该答案做向量检索，缩小问题与文档的语义鸿沟。
- BM25 混合检索：结合稠密向量检索与稀疏关键词检索（BM25），兼顾语义匹配与精确匹配。
- RRF 融合（Reciprocal Rank Fusion）：按排名倒数加权融合多路检索结果，无需归一化分数。
- 重排（Rerank）：用 Cross-Encoder（如 BGE-Reranker）对召回结果精排，提升 Top-K 质量。

## 性能优化

- Embedding 缓存：对相同或语义相近的查询复用检索结果，降低延迟与 API 成本。可结合 LRU 精确缓存与 FAISS 语义近似缓存。
- 检索评估：使用 RAGAS 指标（Faithfulness、Answer Relevancy、Context Precision、Context Recall）离线评估不同策略的效果。
