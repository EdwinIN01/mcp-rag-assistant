# Embedding 模型与重排模型

## Embedding 模型

Embedding 模型将文本映射为稠密向量（dense vector），使语义相近的文本在向量空间中距离更近。它是语义检索和 RAG 的基础。

### BiEncoder（双塔模型）

BiEncoder 将 query 和 document 分别独立编码为向量，再通过余弦相似度计算匹配度。
- 优点：文档可预先编码入库，查询时只需编码 query，速度快
- 缺点：query 和 doc 没有交互，精度有限
- 适用：大规模初筛检索（召回阶段）

典型模型：BGE、text-embedding、sentence-transformers

### CrossEncoder（交叉编码器）

CrossEncoder 将 query 和 document 拼接后共同输入模型，输出匹配分数。
- 优点：query 和 doc 深度交互，精度高
- 缺点：无法预先编码，每次都要前向传播，速度慢
- 适用：小规模精排（重排阶段）

典型模型：bge-reranker、cross-encoder/ms-marco

## 两阶段检索

实际系统常采用两阶段架构：
1. **召回阶段**：用 BiEncoder 从全库快速召回 Top-K 候选（如 Top-100）
2. **精排阶段**：用 CrossEncoder 对候选重排，选出最相关的 Top-N（如 Top-3）

这样兼顾了速度和精度。

## 归一化

Embedding 通常做 L2 归一化（normalize），使内积等价于余弦相似度，便于计算和比较。
