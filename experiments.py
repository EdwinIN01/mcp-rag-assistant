# -*- coding: utf-8 -*-
"""对比实验脚本：自动跑 5 组实验并生成量化报告。

实验内容：
  1. 单路 vs 混合检索（向量 / BM25 / 向量+BM25+RRF）+ MRR / NDCG
  2. 重排前后对比（RRF 融合 vs CrossEncoder 重排）+ MRR
  3. 缓存效果（首次 / 精确重复 / 语义近似）
  4. 切分参数影响（chunk_size 300 vs 600）
  5. 生成层评估（忠实度 + 正确性，LLM-as-Judge，多轮取均值）

运行：
    python experiments.py
报告输出：experiments_report.md
"""
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import config
from rag_engine.loader import DocumentLoader
from rag_engine.splitter import TextSplitter
from rag_engine.vectorstore import VectorStore
from rag_engine.retriever import HybridRetriever

# ---------- 测试集：问题 + 期望来源 + 标准答案 ----------
# 设计原则：含专有名词（BM25占优）/ 语义表述（向量占优）/ 跨文档易混淆 / 负样本
TEST_CASES = [
    # 专有名词类（BM25 应占优）
    {"q": "LoRA 微调的原理是什么？", "expect": "finetuning.md",
     "answer": "LoRA 通过低秩矩阵分解，冻结原模型权重只训练少量附加低秩矩阵，实现高效参数微调。"},
    {"q": "HNSW 是什么索引算法？", "expect": "vector_db.md",
     "answer": "HNSW 是分层可导航小世界图索引，通过多层图结构实现近似最近邻搜索，查询快且精度高。"},
    {"q": "PagedAttention 怎么提升推理效率？", "expect": "llm_inference.md",
     "answer": "PagedAttention 借鉴操作系统分页机制管理 KV 缓存，减少显存碎片，提升推理吞吐。"},
    {"q": "ReAct 框架的 Thought Action Observation 是什么？", "expect": "agent_intro.md",
     "answer": "ReAct 通过 Thought（推理）→ Action（行动）→ Observation（观察）循环实现推理与行动交替。"},
    {"q": "BiEncoder 和 CrossEncoder 有什么区别？", "expect": "embedding_models.md",
     "answer": "BiEncoder 分别编码再算相似度适合召回；CrossEncoder 联合编码精度高适合重排。"},
    # 语义表述类（向量应占优）
    {"q": "怎么写好提示词让模型表现更好？", "expect": "prompt_engineering.md",
     "answer": "通过清晰指令、少样本示例、思维链、角色设定等技巧引导模型输出更准确的结果。"},
    {"q": "如何让大模型推理更快更省显存？", "expect": "llm_inference.md",
     "answer": "通过量化、KV 缓存优化、PagedAttention、连续批处理等降低推理延迟和显存占用。"},
    {"q": "怎么减少大模型的幻觉问题？", "expect": "rag_intro.md",
     "answer": "通过 RAG 引入外部知识、事实校验、置信度评估等方式减少模型编造内容。"},
    # 跨文档 / 易混淆类
    {"q": "知识库问答和模型微调哪个更适合知识更新？", "expect": "finetuning.md",
     "answer": "知识库问答更适合频繁知识更新（只需更新文档），微调适合改变模型固有能力。"},
    {"q": "MCP 协议解决了什么问题？", "expect": "mcp_intro.md",
     "answer": "MCP 协议标准化了 LLM 与外部工具/数据源的连接方式，解决集成碎片化问题。"},
    {"q": "少样本学习是什么？", "expect": "prompt_engineering.md",
     "answer": "少样本学习是通过在提示中提供少量示例引导模型完成任务的提示工程技术。"},
    {"q": "向量数据库的近似最近邻搜索有哪些算法？", "expect": "vector_db.md",
     "answer": "包括 HNSW、IVF、LSH、PQ 等近似最近邻搜索算法，在精度和速度间权衡。"},
    # 补充：细粒度 / 多角度问题
    {"q": "量化技术有哪些？怎么减少模型大小？", "expect": "llm_inference.md",
     "answer": "量化技术包括 INT8/INT4 量化、GPTQ、AWQ 等，通过降低参数精度减少模型大小和推理开销。"},
    {"q": "什么是思维链提示？", "expect": "prompt_engineering.md",
     "answer": "思维链提示是让模型逐步展示推理过程的提示技术，通过分步思考提升复杂推理能力。"},
    {"q": "Agent 和普通 LLM 调用有什么区别？", "expect": "agent_intro.md",
     "answer": "Agent 能自主规划、调用工具、观察反馈并循环执行，普通 LLM 调用是一次性单轮交互。"},
    {"q": "向量数据库选型要考虑哪些因素？", "expect": "vector_db.md",
     "answer": "需考虑检索速度、精度、内存占用、是否支持过滤、持久化、扩展性等因素。"},
    {"q": "RAG 系统的核心组件有哪些？", "expect": "rag_intro.md",
     "answer": "RAG 核心组件包括文档加载、切分、向量化、向量存储、检索、重排和生成。"},
    {"q": "全参数微调为什么成本高？", "expect": "finetuning.md",
     "answer": "全参数微调需更新所有参数，显存和计算开销大，LoRA 等高效微调只训练少量参数。"},
    {"q": "嵌入模型的维度对效果有什么影响？", "expect": "embedding_models.md",
     "answer": "维度越高表达能力越强但计算和存储开销越大，需在效果和效率间权衡。"},
    {"q": "MCP 和 Function Calling 有什么区别？", "expect": "mcp_intro.md",
     "answer": "MCP 是标准化协议连接 LLM 与外部资源，Function Calling 是 LLM 调用函数的能力，MCP 范围更广。"},
    # 负样本类（知识库无法回答，期望检索不应命中相关知识）
    {"q": "今天上海天气怎么样？", "expect": None,
     "answer": "知识库中不包含天气信息，无法回答。"},
    {"q": "如何做红烧肉？", "expect": None,
     "answer": "知识库中不包含菜谱信息，无法回答。"},
    {"q": "Python 列表怎么排序？", "expect": None,
     "answer": "知识库中不包含编程教程，无法回答。"},
    {"q": "2024年诺贝尔物理学奖得主是谁？", "expect": None,
     "answer": "知识库中不包含新闻或奖项信息，无法回答。"},
    {"q": "怎么注册微信小程序？", "expect": None,
     "answer": "知识库中不包含操作教程，无法回答。"},
]

# 正样本（有期望来源）用于检索层评估
POSITIVE_CASES = [tc for tc in TEST_CASES if tc["expect"] is not None]

TOP_K = 5
RUNS = 3  # 生成层评估重复次数（LLM 输出非确定）
REPORT = []


def log(text=""):
    print(text)
    REPORT.append(text)


# ============================================================
# 检索层指标
# ============================================================
def hit_rate(results, expect):
    """Top-K 中是否命中期望来源。"""
    sources = [d.metadata.get("source", "") for d in results]
    return 1 if any(expect in s for s in sources) else 0


def top1_correct(results, expect):
    """Top1 是否来自期望来源。"""
    if not results:
        return 0
    return 1 if expect in results[0].metadata.get("source", "") else 0


def reciprocal_rank(results, expect):
    """MRR 单条贡献：正确文档排名的倒数。未命中为 0。"""
    for i, d in enumerate(results):
        if expect in d.metadata.get("source", ""):
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(results, expect, k=5):
    """NDCG@K：考虑排名位置加权的归一化指标。正确文档越靠前分越高。值域 [0,1]。"""
    # DCG：实际排名下的累计增益
    dcg = 0.0
    num_relevant = 0
    for i, d in enumerate(results[:k]):
        rel = 1.0 if expect in d.metadata.get("source", "") else 0.0
        dcg += rel / math.log2(i + 2)  # i+2 因为 log2(1)=0
        if rel > 0:
            num_relevant += 1
    # IDCG：理想排名（所有相关文档排最前）下的累计增益
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(num_relevant, k)))
    return dcg / idcg if idcg > 0 else 0.0


# ============================================================
# 生成层评估：LLM-as-Judge
# ============================================================
def _llm_chat(messages, temperature=0.3):
    """调用 LLM，无 Key 时返回 None。"""
    if not config.llm_api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(base_url=config.llm_api_base, api_key=config.llm_api_key)
        resp = client.chat.completions.create(
            model=config.llm_model, messages=messages, temperature=temperature,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"  [LLM] 调用失败: {e}")
        return None


def generate_answer(query, context):
    """根据检索上下文生成回答。"""
    messages = [
        {"role": "system", "content":
            "你是一个基于知识库的问答助手。严格遵守以下规则：\n"
            "1. 只能基于用户提供的参考资料回答，不得使用资料之外的知识。\n"
            "2. 在引用处标注 [1] [2] 等编号，确保每个论断都有出处。\n"
            "3. 若参考资料无法回答，明确说明'根据现有资料无法回答'，不得编造。\n"
            "4. 不得对检索内容做超出原文含义的推断或扩展。"},
        {"role": "user", "content":
            f"用户问题：{query}\n\n参考资料：\n{context}\n\n请根据参考资料回答。"},
    ]
    return _llm_chat(messages, temperature=0.1)


def judge_faithfulness(answer, context):
    """LLM-as-Judge：评估答案是否忠于参考资料（无幻觉）。返回 1/0/-1(评估失败)。"""
    if not answer:
        return 0
    messages = [
        {"role": "system", "content":
            "你是评估专家。判断答案中的每个论断是否都能从参考资料中找到依据。"
            '只回答 JSON：{"faithful": 1或0, "reason": "简短理由"}'},
        {"role": "user", "content":
            f"参考资料：\n{context}\n\n答案：\n{answer}\n\n"
            "判断答案是否完全基于参考资料，有无编造。"},
    ]
    result = _llm_chat(messages, temperature=0.0)
    if result:
        try:
            data = json.loads(result.strip().strip("`"))
            return int(data.get("faithful", 0))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return -1


def judge_correctness(answer, question, standard_answer):
    """LLM-as-Judge：评估答案是否正确回答了问题。返回 1/0/-1(评估失败)。"""
    if not answer:
        return 0
    messages = [
        {"role": "system", "content":
            "你是评估专家。判断答案是否正确回答了问题，与标准答案对比。"
            '只回答 JSON：{"correct": 1或0, "reason": "简短理由"}'},
        {"role": "user", "content":
            f"问题：{question}\n\n标准答案：{standard_answer}\n\n待评估答案：{answer}\n\n"
            "判断待评估答案是否正确。"},
    ]
    result = _llm_chat(messages, temperature=0.0)
    if result:
        try:
            data = json.loads(result.strip().strip("`"))
            return int(data.get("correct", 0))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return -1


# ============================================================
# 准备：加载文档入库
def main():
    """执行全部实验并生成报告（import 时不执行，仅暴露 TEST_CASES）。"""
    # ============================================================
    print("=" * 60)
    print("准备阶段：加载示例文档入库")
    print("=" * 60)

    vs = VectorStore(collection_name="exp_main")
    loader = DocumentLoader()
    splitter = TextSplitter()
    docs = loader.load_dir(Path("data/docs"))
    chunks = splitter.split(docs)
    vs.add_documents(chunks)
    print(f"加载 {len(docs)} 文档，切分 {len(chunks)} 片段入库")

    retriever = HybridRetriever(vs)
    retriever._ensure_bm25()
    print("BM25 索引构建完成")

    # 预热重排模型（避免首次重排冷启动耗时飙升）
    if config.reranker_model:
        print(f"预热重排模型: {config.reranker_model} ...")
        retriever.warmup_reranker()
        print("重排模型预热完成")
    print()

    # ============================================================
    # 实验 1：单路 vs 混合检索
    # ============================================================
    log("# MCP-RAG 对比实验报告")
    log()
    log("## 实验 1：单路检索 vs 混合检索（RRF 融合）")
    log()
    log("| 问题 | 期望来源 | 向量Top1 | BM25 Top1 | 混合Top1 | 向量命中 | BM25命中 | 混合命中 |")
    log("|------|---------|---------|----------|---------|---------|---------|---------|")

    vec_hits = bm25_hits = fused_hits = 0
    vec_top1 = bm25_top1 = fused_top1 = 0
    vec_mrr = bm25_mrr = fused_mrr = 0.0
    vec_ndcg = bm25_ndcg = fused_ndcg = 0.0

    for tc in POSITIVE_CASES:
        q, expect = tc["q"], tc["expect"]
        vec_results = vs.similarity_search_with_score(q, k=TOP_K)
        vec_docs = [d for d, _ in vec_results]
        bm25_results = retriever._bm25_search(q, k=TOP_K)
        bm25_docs = [d for d, _ in bm25_results]
        fused = retriever._rrf_fuse(
            [(d, float(s)) for d, s in vec_results], bm25_results
        )
        fused_docs = [d for d, _ in fused[:TOP_K]]

        v_hit = hit_rate(vec_docs, expect)
        b_hit = hit_rate(bm25_docs, expect)
        f_hit = hit_rate(fused_docs, expect)
        v_t1 = top1_correct(vec_docs, expect)
        b_t1 = top1_correct(bm25_docs, expect)
        f_t1 = top1_correct(fused_docs, expect)
        v_rr = reciprocal_rank(vec_docs, expect)
        b_rr = reciprocal_rank(bm25_docs, expect)
        f_rr = reciprocal_rank(fused_docs, expect)
        v_nd = ndcg_at_k(vec_docs, expect, TOP_K)
        b_nd = ndcg_at_k(bm25_docs, expect, TOP_K)
        f_nd = ndcg_at_k(fused_docs, expect, TOP_K)

        vec_hits += v_hit; bm25_hits += b_hit; fused_hits += f_hit
        vec_top1 += v_t1; bm25_top1 += b_t1; fused_top1 += f_t1
        vec_mrr += v_rr; bm25_mrr += b_rr; fused_mrr += f_rr
        vec_ndcg += v_nd; bm25_ndcg += b_nd; fused_ndcg += f_nd

        v_src = vec_docs[0].metadata.get("source", "?")[:12] if vec_docs else "-"
        b_src = bm25_docs[0].metadata.get("source", "?")[:12] if bm25_docs else "-"
        f_src = fused_docs[0].metadata.get("source", "?")[:12] if fused_docs else "-"
        log(f"| {q[:14]} | {expect[:10]} | {v_src} | {b_src} | {f_src} | {v_hit} | {b_hit} | {f_hit} |")

    n = len(POSITIVE_CASES)
    log()
    log(f"**命中率（Top-{TOP_K} 含正确来源）**：")
    log(f"- 向量检索：{vec_hits}/{n} = {vec_hits/n*100:.1f}%")
    log(f"- BM25 检索：{bm25_hits}/{n} = {bm25_hits/n*100:.1f}%")
    log(f"- 混合检索（RRF）：{fused_hits}/{n} = {fused_hits/n*100:.1f}%")
    log()
    log(f"**Top1 准确率**：")
    log(f"- 向量检索：{vec_top1}/{n} = {vec_top1/n*100:.1f}%")
    log(f"- BM25 检索：{bm25_top1}/{n} = {bm25_top1/n*100:.1f}%")
    log(f"- 混合检索（RRF）：{fused_top1}/{n} = {fused_top1/n*100:.1f}%")
    log()
    log(f"**MRR（平均倒数排名，越高越好）**：")
    log(f"- 向量检索：{vec_mrr/n:.4f}")
    log(f"- BM25 检索：{bm25_mrr/n:.4f}")
    log(f"- 混合检索（RRF）：{fused_mrr/n:.4f}")
    log()
    log(f"**NDCG@{TOP_K}（归一化折损累计增益，越高越好）**：")
    log(f"- 向量检索：{vec_ndcg/n:.4f}")
    log(f"- BM25 检索：{bm25_ndcg/n:.4f}")
    log(f"- 混合检索（RRF）：{fused_ndcg/n:.4f}")
    log()

    # ============================================================
    # 实验 2：重排前后对比
    # ============================================================
    log("## 实验 2：重排前后对比（RRF 融合 vs CrossEncoder 重排）")
    log()
    log("| 问题 | 重排前Top1 | 重排后Top1 | Top1变化 | 重排MRR | 重排耗时 |")
    log("|------|-----------|-----------|---------|---------|---------|")

    rerank_changes = 0
    rerank_top1_correct = 0
    rerank_mrr = 0.0
    total_rerank_time = 0

    for tc in POSITIVE_CASES:
        q, expect = tc["q"], tc["expect"]
        vec_results = vs.similarity_search_with_score(q, k=TOP_K)
        bm25_results = retriever._bm25_search(q, k=TOP_K)
        fused = retriever._rrf_fuse(
            [(d, float(s)) for d, s in vec_results], bm25_results
        )
        fused_docs = [d for d, _ in fused[:TOP_K]]

        t0 = time.time()
        reranked = retriever._rerank(q, fused_docs, top_k=3)
        rt = time.time() - t0
        total_rerank_time += rt

        before_src = fused_docs[0].metadata.get("source", "?")[:12] if fused_docs else "-"
        after_src = reranked[0].metadata.get("source", "?")[:12] if reranked else "-"
        changed = "是" if before_src != after_src else "否"
        if before_src != after_src:
            rerank_changes += 1
        rerank_top1_correct += top1_correct(reranked, expect)
        rr = reciprocal_rank(reranked, expect)
        rerank_mrr += rr

        log(f"| {q[:14]} | {before_src} | {after_src} | {changed} | {rr:.4f} | {rt*1000:.0f}ms |")

    log()
    log(f"**重排效果**：")
    log(f"- Top1 顺序发生变化的题目：{rerank_changes}/{n}")
    log(f"- 重排后 Top1 准确率：{rerank_top1_correct}/{n} = {rerank_top1_correct/n*100:.1f}%")
    log(f"- 重排后 Top1 准确率 vs 混合检索 Top1：{rerank_top1_correct/n*100:.1f}% vs {fused_top1/n*100:.1f}%")
    log(f"- 重排后 MRR vs 混合检索 MRR：{rerank_mrr/n:.4f} vs {fused_mrr/n:.4f}")
    log(f"- 平均重排耗时：{total_rerank_time/n*1000:.0f}ms")
    log()

    # ============================================================
    # 实验 3：缓存效果
    # ============================================================
    log("## 实验 3：缓存效果（LRU 精确缓存 + FAISS 语义缓存）")
    log()

    q0 = POSITIVE_CASES[0]["q"]
    t0 = time.perf_counter()
    retriever.retrieve(q0)
    t_first = time.perf_counter() - t0

    # 缓存命中跑多次取平均，避免计时精度问题
    t0 = time.perf_counter()
    for _ in range(100):
        retriever.retrieve(q0)  # 完全相同 → LRU 命中
    t_lru = (time.perf_counter() - t0) / 100

    q_similar = "RAG 的检索优化方法有哪些？"  # 语义相近
    t0 = time.perf_counter()
    retriever.retrieve(q_similar)
    t_semantic = time.perf_counter() - t0

    stats = retriever.cache.stats()
    log(f"| 查询类型 | 耗时 |")
    log(f"|---------|------|")
    log(f"| 首次查询（无缓存） | {t_first*1000:.0f}ms |")
    log(f"| 精确重复查询（LRU命中） | {t_lru*1000:.1f}ms |")
    log(f"| 语义相近查询（FAISS命中） | {t_semantic*1000:.1f}ms |")
    log()
    log(f"**加速比**：")
    log(f"- LRU 精确缓存：{t_first/t_lru:.0f}x 加速")
    log(f"- FAISS 语义缓存：{t_first/t_semantic:.1f}x 加速")
    log(f"- 缓存状态：精确 {stats['exact_size']} 条，语义索引 {stats['semantic_size']} 条")
    log()

    # ============================================================
    # 实验 4：切分参数影响
    # ============================================================
    log("## 实验 4：切分参数影响（chunk_size 300 vs 600）")
    log()

    results_300 = {}
    results_600 = {}
    for size in [300, 600]:
        vs_tmp = VectorStore(collection_name=f"exp_chunk_{size}")
        sp_tmp = TextSplitter(chunk_size=size, chunk_overlap=50)
        chunks_tmp = sp_tmp.split(loader.load_dir(Path("data/docs")))
        vs_tmp.add_documents(chunks_tmp)
        ret_tmp = HybridRetriever(vs_tmp)
        ret_tmp._ensure_bm25()
        for tc in POSITIVE_CASES:
            res = ret_tmp.retrieve(tc["q"], k=3)
            hit = hit_rate(res, tc["expect"])
            t1 = top1_correct(res, tc["expect"])
            rr = reciprocal_rank(res, tc["expect"])
            if size == 300:
                results_300[tc["q"]] = (hit, t1, rr, len(chunks_tmp))
            else:
                results_600[tc["q"]] = (hit, t1, rr, len(chunks_tmp))

    h300 = sum(v[0] for v in results_300.values())
    h600 = sum(v[0] for v in results_600.values())
    t300 = sum(v[1] for v in results_300.values())
    t600 = sum(v[1] for v in results_600.values())
    m300 = sum(v[2] for v in results_300.values())
    m600 = sum(v[2] for v in results_600.values())
    c300 = list(results_300.values())[0][3]
    c600 = list(results_600.values())[0][3]

    log(f"| 指标 | chunk_size=300 | chunk_size=600 |")
    log(f"|------|---------------|---------------|")
    log(f"| 切分片段数 | {c300} | {c600} |")
    log(f"| 命中率（Top3） | {h300}/{n} = {h300/n*100:.1f}% | {h600}/{n} = {h600/n*100:.1f}% |")
    log(f"| Top1 准确率 | {t300}/{n} = {t300/n*100:.1f}% | {t600}/{n} = {t600/n*100:.1f}% |")
    log(f"| MRR | {m300/n:.4f} | {m600/n:.4f} |")
    log()
    log("**结论**：chunk_size 较小时片段更细，命中率高但上下文可能不完整；较大时上下文完整但可能引入噪声。需根据文档类型权衡。")
    log()

    # ============================================================
    # 实验 5：生成层评估（忠实度 + 正确性，LLM-as-Judge）
    # ============================================================
    log("## 实验 5：生成层评估（忠实度 + 正确性，LLM-as-Judge）")
    log()

    if not config.llm_api_key:
        log("> 未配置 LLM_API_KEY，跳过生成层评估。")
        log("> 配置后可评估：答案忠实度（无幻觉）、答案正确性、负样本拒绝率。")
        log()
    else:
        log(f"测试集：{len(TEST_CASES)} 题（正样本 {len(POSITIVE_CASES)} + 负样本 "
            f"{len(TEST_CASES) - len(POSITIVE_CASES)}），每题重复 {RUNS} 次取多数投票。")
        log()
        log("| 问题 | 类型 | 忠实度 | 正确性 |")
        log("|------|------|--------|--------|")

        total_faith = 0
        total_correct = 0
        total_evaluated = 0
        pos_faith = 0
        pos_correct = 0
        pos_count = 0
        neg_refused = 0
        neg_count = 0

        for tc in TEST_CASES:
            q = tc["q"]
            is_negative = tc["expect"] is None
            qtype = "负样本" if is_negative else "正样本"

            # 检索 + 构建 context
            docs = retriever.retrieve(q, k=3)
            if docs:
                context = "\n\n".join(
                    f"[{i+1}] {d.page_content}" for i, d in enumerate(docs)
                )
            else:
                context = "（未检索到相关内容）"

            # 多轮生成 + 评估，取多数投票
            faith_votes = []
            correct_votes = []

            for run_idx in range(RUNS):
                print(f"  [{q[:16]}...] 第 {run_idx+1}/{RUNS} 轮...", end="\r")
                answer = generate_answer(q, context)
                if answer is None:
                    answer = ""

                f_score = judge_faithfulness(answer, context)
                c_score = judge_correctness(answer, q, tc["answer"])

                if f_score >= 0:
                    faith_votes.append(f_score)
                if c_score >= 0:
                    correct_votes.append(c_score)

            # 多数投票：>= 半数通过则为 1
            faith = 1 if faith_votes and sum(faith_votes) >= len(faith_votes) / 2 else 0
            correct = 1 if correct_votes and sum(correct_votes) >= len(correct_votes) / 2 else 0

            if faith_votes and correct_votes:
                total_evaluated += 1
                total_faith += faith
                total_correct += correct
                if is_negative:
                    neg_count += 1
                    neg_refused += correct  # 负样本正确 = 正确拒绝
                else:
                    pos_count += 1
                    pos_faith += faith
                    pos_correct += correct

            log(f"| {q[:14]} | {qtype} | {faith} | {correct} |")

        log()
        log(f"**生成层评估结果**（{total_evaluated} 题有效评估）：")
        if total_evaluated > 0:
            log(f"- 整体忠实度（Faithfulness）：{total_faith}/{total_evaluated} = {total_faith/total_evaluated*100:.1f}%")
            log(f"- 整体正确性（Correctness）：{total_correct}/{total_evaluated} = {total_correct/total_evaluated*100:.1f}%")
            if pos_count > 0:
                log(f"- 正样本忠实度：{pos_faith}/{pos_count} = {pos_faith/pos_count*100:.1f}%")
                log(f"- 正样本正确性：{pos_correct}/{pos_count} = {pos_correct/pos_count*100:.1f}%")
            if neg_count > 0:
                log(f"- 负样本拒绝率（正确拒答）：{neg_refused}/{neg_count} = {neg_refused/neg_count*100:.1f}%")
            log()
            log("> 忠实度：答案是否完全基于检索内容，无幻觉编造。")
            log("> 正确性：答案是否正确回答了问题（与标准答案对比）。")
            log("> 负样本拒绝率：知识库无法回答的问题中，LLM 正确拒答的比例。")
        log()

    # ============================================================
    # 写报告
    # ============================================================
    report_path = Path("experiments_report.md")
    report_path.write_text("\n".join(REPORT), encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"报告已生成：{report_path.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
