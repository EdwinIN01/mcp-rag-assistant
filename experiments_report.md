# MCP-RAG 对比实验报告

## 实验 1：单路检索 vs 混合检索（RRF 融合）

| 问题 | 期望来源 | 向量Top1 | BM25 Top1 | 混合Top1 | 向量命中 | BM25命中 | 混合命中 |
|------|---------|---------|----------|---------|---------|---------|---------|
| LoRA 微调的原理是什么？ | finetuning | data\docs\fi | data\docs\fi | data\docs\fi | 1 | 1 | 1 |
| HNSW 是什么索引算法？ | vector_db. | data\docs\ve | data\docs\ve | data\docs\ra | 1 | 1 | 1 |
| PagedAttention | llm_infere | data\docs\ll | data\docs\ll | data\docs\ra | 1 | 1 | 1 |
| ReAct 框架的 Thou | agent_intr | data\docs\ag | data\docs\ag | data\docs\ag | 1 | 1 | 1 |
| BiEncoder 和 Cr | embedding_ | data\docs\em | data\docs\em | data\docs\em | 1 | 1 | 1 |
| 怎么写好提示词让模型表现更好 | prompt_eng | data\docs\pr | data\docs\pr | data\docs\mc | 1 | 1 | 1 |
| 如何让大模型推理更快更省显存 | llm_infere | data\docs\ll | data\docs\ll | data\docs\ll | 1 | 1 | 1 |
| 怎么减少大模型的幻觉问题？ | rag_intro. | data\docs\ll | data\docs\ll | data\docs\ra | 0 | 1 | 1 |
| 知识库问答和模型微调哪个更适 | finetuning | data\docs\fi | data\docs\fi | data\docs\fi | 1 | 1 | 1 |
| MCP 协议解决了什么问题？ | mcp_intro. | data\docs\mc | data\docs\mc | data\docs\mc | 1 | 1 | 1 |
| 少样本学习是什么？ | prompt_eng | data\docs\pr | data\docs\pr | data\docs\pr | 1 | 1 | 1 |
| 向量数据库的近似最近邻搜索有 | vector_db. | data\docs\ve | data\docs\ve | data\docs\ra | 1 | 1 | 1 |

**命中率（Top-5 含正确来源）**：
- 向量检索：11/12 = 91.7%
- BM25 检索：12/12 = 100.0%
- 混合检索（RRF）：12/12 = 100.0%

**Top1 准确率**：
- 向量检索：11/12 = 91.7%
- BM25 检索：11/12 = 91.7%
- 混合检索（RRF）：8/12 = 66.7%

## 实验 2：重排前后对比（RRF 融合 vs CrossEncoder 重排）

| 问题 | 重排前Top1 | 重排后Top1 | Top1变化 | 重排耗时 |
|------|-----------|-----------|---------|---------|
| LoRA 微调的原理是什么？ | data\docs\fi | data\docs\fi | 否 | 8830ms |
| HNSW 是什么索引算法？ | data\docs\ra | data\docs\ve | 是 | 3937ms |
| PagedAttention | data\docs\ra | data\docs\ll | 是 | 3600ms |
| ReAct 框架的 Thou | data\docs\ag | data\docs\ag | 否 | 2388ms |
| BiEncoder 和 Cr | data\docs\em | data\docs\em | 否 | 447ms |
| 怎么写好提示词让模型表现更好 | data\docs\mc | data\docs\pr | 是 | 443ms |
| 如何让大模型推理更快更省显存 | data\docs\ll | data\docs\ll | 否 | 441ms |
| 怎么减少大模型的幻觉问题？ | data\docs\ra | data\docs\ra | 否 | 1617ms |
| 知识库问答和模型微调哪个更适 | data\docs\fi | data\docs\fi | 否 | 422ms |
| MCP 协议解决了什么问题？ | data\docs\mc | data\docs\mc | 否 | 260ms |
| 少样本学习是什么？ | data\docs\pr | data\docs\pr | 否 | 442ms |
| 向量数据库的近似最近邻搜索有 | data\docs\ra | data\docs\ve | 是 | 466ms |

**重排效果**：
- Top1 顺序发生变化的题目：4/12
- 重排后 Top1 准确率：12/12 = 100.0%
- 重排后 Top1 准确率 vs 混合检索 Top1：100.0% vs 66.7%
- 平均重排耗时：1941ms

## 实验 3：缓存效果（LRU 精确缓存 + FAISS 语义缓存）

| 查询类型 | 耗时 |
|---------|------|
| 首次查询（无缓存） | 613ms |
| 精确重复查询（LRU命中） | 0.0ms |
| 语义相近查询（FAISS命中） | 478.3ms |

**加速比**：
- LRU 精确缓存：166393x 加速
- FAISS 语义缓存：1.3x 加速
- 缓存状态：精确 2 条，语义索引 2 条

## 实验 4：切分参数影响（chunk_size 300 vs 600）

| 指标 | chunk_size=300 | chunk_size=600 |
|------|---------------|---------------|
| 切分片段数 | 27 | 14 |
| 命中率（Top3） | 12/12 = 100.0% | 12/12 = 100.0% |
| Top1 准确率 | 12/12 = 100.0% | 12/12 = 100.0% |

**结论**：chunk_size 较小时片段更细，命中率高但上下文可能不完整；较大时上下文完整但可能引入噪声。需根据文档类型权衡。
