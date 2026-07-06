# 向量数据库

## 什么是向量数据库

向量数据库（Vector Database）是专门用于存储、索引和检索高维向量的数据库系统，是 RAG 和语义检索的核心基础设施。

## 常见索引算法

### 1. HNSW（Hierarchical Navigable Small World）
分层可导航小世界图，通过构建多层图结构实现高效近似最近邻搜索。查询速度快、召回率高，是当前最流行的 ANN 索引。

### 2. IVF（Inverted File Index）
倒排文件索引，通过聚类将向量空间划分为多个桶（cluster），查询时只搜索最近的几个桶，加速检索。

### 3. Flat（暴力检索）
精确计算所有向量的距离，无近似。准确但慢，适合小规模数据。

### 4. PQ（Product Quantization）
乘积量化，将向量压缩以减少内存占用，牺牲少量精度换取存储效率。

## 主流向量数据库对比

| 数据库 | 特点 |
|--------|------|
| Chroma | 轻量易用，适合原型开发 |
| Milvus | 分布式，适合大规模生产 |
| FAISS | Meta 开源库，高性能计算 |
| Pinecone | 云托管，免运维 |
| Qdrant | Rust 编写，高性能 |

## 选型考虑

- 数据规模：小规模用 Chroma/FAISS，大规模用 Milvus
- 部署方式：本地用 FAISS，云上用 Pinecone
- 是否需要持久化：Chroma 支持本地持久化
