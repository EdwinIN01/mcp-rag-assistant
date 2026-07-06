# MCP-RAG 对比实验报告

## 实验 1：单路检索 vs 混合检索（RRF 融合）

| 问题 | 期望来源 | 向量Top1 | BM25 Top1 | 混合Top1 | 向量命中 | BM25命中 | 混合命中 |
|------|---------|---------|----------|---------|---------|---------|---------|
| RAG 有哪些检索优化策略？ | rag_intro. | data\docs\ra | data\docs\ra | data\docs\ra | 1 | 1 | 1 |
| 什么是 RAG 检索增强生成 | rag_intro. | data\docs\ra | data\docs\ra | data\docs\ra | 1 | 1 | 1 |
| RRF 融合是怎么工作的？ | rag_intro. | data\docs\ra | data\docs\ra | data\docs\ra | 1 | 1 | 1 |
| Embedding 缓存有什 | rag_intro. | data\docs\ra | data\docs\ra | data\docs\ra | 1 | 1 | 1 |
| 什么是 MCP 协议？ | mcp_intro. | data\docs\mc | data\docs\mc | data\docs\mc | 1 | 1 | 1 |
| MCP 和 Function | mcp_intro. | data\docs\mc | data\docs\mc | data\docs\mc | 1 | 1 | 1 |
| MCP 有哪些核心概念？ | mcp_intro. | data\docs\mc | data\docs\mc | data\docs\mc | 1 | 1 | 1 |
| MCP 的典型应用场景有哪些 | mcp_intro. | data\docs\mc | data\docs\mc | data\docs\mc | 1 | 1 | 1 |

**命中率（Top-5 含正确来源）**：
- 向量检索：8/8 = 100.0%
- BM25 检索：8/8 = 100.0%
- 混合检索（RRF）：8/8 = 100.0%

**Top1 准确率**：
- 向量检索：8/8 = 100.0%
- BM25 检索：8/8 = 100.0%
- 混合检索（RRF）：8/8 = 100.0%

## 实验 2：重排前后对比（RRF 融合 vs CrossEncoder 重排）

| 问题 | 重排前Top1 | 重排后Top1 | Top1变化 | 重排耗时 |
|------|-----------|-----------|---------|---------|
| RAG 有哪些检索优化策略？ | data\docs\ra | data\docs\ra | 否 | 2036ms |
| 什么是 RAG 检索增强生成 | data\docs\ra | data\docs\ra | 否 | 268ms |
| RRF 融合是怎么工作的？ | data\docs\ra | data\docs\ra | 否 | 355ms |
| Embedding 缓存有什 | data\docs\ra | data\docs\ra | 否 | 395ms |
| 什么是 MCP 协议？ | data\docs\mc | data\docs\mc | 否 | 285ms |
| MCP 和 Function | data\docs\mc | data\docs\mc | 否 | 304ms |
| MCP 有哪些核心概念？ | data\docs\mc | data\docs\mc | 否 | 370ms |
| MCP 的典型应用场景有哪些 | data\docs\mc | data\docs\mc | 否 | 287ms |

**重排效果**：
- Top1 顺序发生变化的题目：0/8
- 重排后 Top1 准确率：8/8 = 100.0%
- 重排后 Top1 准确率 vs 混合检索 Top1：100.0% vs 100.0%
- 平均重排耗时：537ms

## 实验 3：缓存效果（LRU 精确缓存 + FAISS 语义缓存）

| 查询类型 | 耗时 |
|---------|------|
| 首次查询（无缓存） | 366ms |
| 精确重复查询（LRU命中） | 0.0ms |
| 语义相近查询（FAISS命中） | 25.3ms |

**加速比**：
- LRU 精确缓存：107834x 加速
- FAISS 语义缓存：14.4x 加速
- 缓存状态：精确 1 条，语义索引 1 条

## 实验 4：切分参数影响（chunk_size 300 vs 600）

| 指标 | chunk_size=300 | chunk_size=600 |
|------|---------------|---------------|
| 切分片段数 | 9 | 4 |
| 命中率（Top3） | 8/8 = 100.0% | 8/8 = 100.0% |
| Top1 准确率 | 8/8 = 100.0% | 8/8 = 100.0% |

**结论**：chunk_size 较小时片段更细，命中率高但上下文可能不完整；较大时上下文完整但可能引入噪声。需根据文档类型权衡。
