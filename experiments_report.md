# MCP-RAG 对比实验报告

## 实验 1：单路检索 vs 混合检索（RRF 融合）

| 问题 | 期望来源 | 向量Top1 | BM25 Top1 | 混合Top1 | 向量命中 | BM25命中 | 混合命中 |
|------|---------|---------|----------|---------|---------|---------|---------|
| LoRA 微调的原理是什么？ | finetuning | data\docs\fi | data\docs\fi | data\docs\fi | 1 | 1 | 1 |
| HNSW 是什么索引算法？ | vector_db. | data\docs\ve | data\docs\ve | data\docs\ve | 1 | 1 | 1 |
| PagedAttention | llm_infere | data\docs\ll | data\docs\ll | data\docs\ll | 1 | 1 | 1 |
| ReAct 框架的 Thou | agent_intr | data\docs\ag | data\docs\ag | data\docs\ag | 1 | 1 | 1 |
| BiEncoder 和 Cr | embedding_ | data\docs\em | data\docs\em | data\docs\em | 1 | 1 | 1 |
| 怎么写好提示词让模型表现更好 | prompt_eng | data\docs\pr | data\docs\pr | data\docs\pr | 1 | 1 | 1 |
| 如何让大模型推理更快更省显存 | llm_infere | data\docs\ll | data\docs\ll | data\docs\ll | 1 | 1 | 1 |
| 怎么减少大模型的幻觉问题？ | rag_intro. | data\docs\ll | data\docs\ll | data\docs\ll | 0 | 1 | 1 |
| 知识库问答和模型微调哪个更适 | finetuning | data\docs\fi | data\docs\fi | data\docs\fi | 1 | 1 | 1 |
| MCP 协议解决了什么问题？ | mcp_intro. | data\docs\mc | data\docs\mc | data\docs\mc | 1 | 1 | 1 |
| 少样本学习是什么？ | prompt_eng | data\docs\pr | data\docs\pr | data\docs\pr | 1 | 1 | 1 |
| 向量数据库的近似最近邻搜索有 | vector_db. | data\docs\ve | data\docs\ve | data\docs\ve | 1 | 1 | 1 |
| 量化技术有哪些？怎么减少模型 | llm_infere | data\docs\fi | data\docs\ll | data\docs\fi | 1 | 1 | 1 |
| 什么是思维链提示？ | prompt_eng | data\docs\pr | data\docs\pr | data\docs\pr | 1 | 1 | 1 |
| Agent 和普通 LLM  | agent_intr | data\docs\ag | data\docs\ag | data\docs\ag | 1 | 1 | 1 |
| 向量数据库选型要考虑哪些因素 | vector_db. | data\docs\ve | data\docs\ve | data\docs\ve | 1 | 1 | 1 |
| RAG 系统的核心组件有哪些 | rag_intro. | data\docs\ra | data\docs\em | data\docs\ra | 1 | 0 | 1 |
| 全参数微调为什么成本高？ | finetuning | data\docs\fi | data\docs\fi | data\docs\fi | 1 | 1 | 1 |
| 嵌入模型的维度对效果有什么影 | embedding_ | data\docs\fi | data\docs\ra | data\docs\ra | 1 | 0 | 1 |
| MCP 和 Function | mcp_intro. | data\docs\mc | data\docs\mc | data\docs\mc | 1 | 1 | 1 |

**命中率（Top-5 含正确来源）**：
- 向量检索：19/20 = 95.0%
- BM25 检索：18/20 = 90.0%
- 混合检索（RRF）：20/20 = 100.0%

**Top1 准确率**：
- 向量检索：17/20 = 85.0%
- BM25 检索：17/20 = 85.0%
- 混合检索（RRF）：17/20 = 85.0%

**MRR（平均倒数排名，越高越好）**：
- 向量检索：0.8700
- BM25 检索：0.8600
- 混合检索（RRF）：0.9083

**NDCG@5（归一化折损累计增益，越高越好）**：
- 向量检索：0.8887
- BM25 检索：0.8693
- 混合检索（RRF）：0.9315

## 实验 2：重排前后对比（RRF 融合 vs CrossEncoder 重排）

| 问题 | 重排前Top1 | 重排后Top1 | Top1变化 | 重排MRR | 重排耗时 |
|------|-----------|-----------|---------|---------|---------|
| LoRA 微调的原理是什么？ | data\docs\fi | data\docs\fi | 否 | 1.0000 | 3290ms |
| HNSW 是什么索引算法？ | data\docs\ve | data\docs\ve | 否 | 1.0000 | 3098ms |
| PagedAttention | data\docs\ll | data\docs\ll | 否 | 1.0000 | 2444ms |
| ReAct 框架的 Thou | data\docs\ag | data\docs\ag | 否 | 1.0000 | 2406ms |
| BiEncoder 和 Cr | data\docs\em | data\docs\em | 否 | 1.0000 | 2407ms |
| 怎么写好提示词让模型表现更好 | data\docs\pr | data\docs\pr | 否 | 1.0000 | 2879ms |
| 如何让大模型推理更快更省显存 | data\docs\ll | data\docs\ll | 否 | 1.0000 | 2699ms |
| 怎么减少大模型的幻觉问题？ | data\docs\ll | data\docs\ra | 是 | 1.0000 | 2767ms |
| 知识库问答和模型微调哪个更适 | data\docs\fi | data\docs\fi | 否 | 1.0000 | 2158ms |
| MCP 协议解决了什么问题？ | data\docs\mc | data\docs\mc | 否 | 1.0000 | 1085ms |
| 少样本学习是什么？ | data\docs\pr | data\docs\pr | 否 | 1.0000 | 2993ms |
| 向量数据库的近似最近邻搜索有 | data\docs\ve | data\docs\ve | 否 | 1.0000 | 2670ms |
| 量化技术有哪些？怎么减少模型 | data\docs\fi | data\docs\ll | 是 | 1.0000 | 2565ms |
| 什么是思维链提示？ | data\docs\pr | data\docs\pr | 否 | 1.0000 | 3664ms |
| Agent 和普通 LLM  | data\docs\ag | data\docs\ag | 否 | 1.0000 | 2597ms |
| 向量数据库选型要考虑哪些因素 | data\docs\ve | data\docs\ve | 否 | 1.0000 | 2888ms |
| RAG 系统的核心组件有哪些 | data\docs\ra | data\docs\ra | 否 | 1.0000 | 2449ms |
| 全参数微调为什么成本高？ | data\docs\fi | data\docs\fi | 否 | 1.0000 | 967ms |
| 嵌入模型的维度对效果有什么影 | data\docs\ra | data\docs\em | 是 | 1.0000 | 2397ms |
| MCP 和 Function | data\docs\mc | data\docs\mc | 否 | 1.0000 | 412ms |

**重排效果**：
- Top1 顺序发生变化的题目：3/20
- 重排后 Top1 准确率：20/20 = 100.0%
- 重排后 Top1 准确率 vs 混合检索 Top1：100.0% vs 85.0%
- 重排后 MRR vs 混合检索 MRR：1.0000 vs 0.9083
- 平均重排耗时：2442ms

## 实验 3：缓存效果（LRU 精确缓存 + FAISS 语义缓存）

| 查询类型 | 耗时 |
|---------|------|
| 首次查询（无缓存） | 4835ms |
| 精确重复查询（LRU命中） | 0.1ms |
| 语义相近查询（FAISS命中） | 5654.8ms |

**加速比**：
- LRU 精确缓存：57357x 加速
- FAISS 语义缓存：0.9x 加速
- 缓存状态：精确 2 条，语义索引 2 条

## 实验 4：切分参数影响（chunk_size 300 vs 600）

| 指标 | chunk_size=300 | chunk_size=600 |
|------|---------------|---------------|
| 切分片段数 | 27 | 14 |
| 命中率（Top3） | 20/20 = 100.0% | 20/20 = 100.0% |
| Top1 准确率 | 20/20 = 100.0% | 20/20 = 100.0% |
| MRR | 1.0000 | 1.0000 |

**结论**：chunk_size 较小时片段更细，命中率高但上下文可能不完整；较大时上下文完整但可能引入噪声。需根据文档类型权衡。

## 实验 5：生成层评估（忠实度 + 正确性，LLM-as-Judge）

测试集：25 题（正样本 20 + 负样本 5），每题重复 3 次取多数投票。

| 问题 | 类型 | 忠实度 | 正确性 |
|------|------|--------|--------|
| LoRA 微调的原理是什么？ | 正样本 | 1 | 1 |
| HNSW 是什么索引算法？ | 正样本 | 1 | 1 |
| PagedAttention | 正样本 | 1 | 1 |
| ReAct 框架的 Thou | 正样本 | 1 | 1 |
| BiEncoder 和 Cr | 正样本 | 1 | 1 |
| 怎么写好提示词让模型表现更好 | 正样本 | 1 | 1 |
| 如何让大模型推理更快更省显存 | 正样本 | 1 | 1 |
| 怎么减少大模型的幻觉问题？ | 正样本 | 1 | 1 |
| 知识库问答和模型微调哪个更适 | 正样本 | 1 | 1 |
| MCP 协议解决了什么问题？ | 正样本 | 1 | 1 |
| 少样本学习是什么？ | 正样本 | 1 | 1 |
| 向量数据库的近似最近邻搜索有 | 正样本 | 1 | 1 |
| 量化技术有哪些？怎么减少模型 | 正样本 | 1 | 1 |
| 什么是思维链提示？ | 正样本 | 1 | 1 |
| Agent 和普通 LLM  | 正样本 | 1 | 1 |
| 向量数据库选型要考虑哪些因素 | 正样本 | 1 | 1 |
| RAG 系统的核心组件有哪些 | 正样本 | 1 | 1 |
| 全参数微调为什么成本高？ | 正样本 | 1 | 1 |
| 嵌入模型的维度对效果有什么影 | 正样本 | 1 | 0 |
| MCP 和 Function | 正样本 | 1 | 1 |
| 今天上海天气怎么样？ | 负样本 | 1 | 1 |
| 如何做红烧肉？ | 负样本 | 1 | 1 |
| Python 列表怎么排序？ | 负样本 | 1 | 1 |
| 2024年诺贝尔物理学奖得主 | 负样本 | 1 | 1 |
| 怎么注册微信小程序？ | 负样本 | 1 | 1 |

**生成层评估结果**（25 题有效评估）：
- 整体忠实度（Faithfulness）：25/25 = 100.0%
- 整体正确性（Correctness）：24/25 = 96.0%
- 正样本忠实度：20/20 = 100.0%
- 正样本正确性：19/20 = 95.0%
- 负样本拒绝率（正确拒答）：5/5 = 100.0%

> 忠实度：答案是否完全基于检索内容，无幻觉编造。
> 正确性：答案是否正确回答了问题（与标准答案对比）。
> 负样本拒绝率：知识库无法回答的问题中，LLM 正确拒答的比例。
