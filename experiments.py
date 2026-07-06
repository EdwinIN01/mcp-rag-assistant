# -*- coding: utf-8 -*-
"""对比实验脚本：自动跑 4 组实验并生成量化报告。

实验内容：
  1. 单路 vs 混合检索（向量 / BM25 / 向量+BM25+RRF）
  2. 重排前后对比（RRF 融合 vs CrossEncoder 重排）
  3. 缓存效果（首次 / 精确重复 / 语义近似）
  4. 切分参数影响（chunk_size 300 vs 600）

运行：
    python experiments.py
报告输出：experiments_report.md
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag_engine.loader import DocumentLoader
from rag_engine.splitter import TextSplitter
from rag_engine.vectorstore import VectorStore
from rag_engine.retriever import HybridRetriever

# ---------- 测试集：问题 + 期望来源 ----------
TEST_CASES = [
    {"q": "RAG 有哪些检索优化策略？", "expect": "rag_intro.md"},
    {"q": "什么是 RAG 检索增强生成？", "expect": "rag_intro.md"},
    {"q": "RRF 融合是怎么工作的？", "expect": "rag_intro.md"},
    {"q": "Embedding 缓存有什么作用？", "expect": "rag_intro.md"},
    {"q": "什么是 MCP 协议？", "expect": "mcp_intro.md"},
    {"q": "MCP 和 Function Calling 有什么区别？", "expect": "mcp_intro.md"},
    {"q": "MCP 有哪些核心概念？", "expect": "mcp_intro.md"},
    {"q": "MCP 的典型应用场景有哪些？", "expect": "mcp_intro.md"},
]

TOP_K = 5
REPORT = []


def log(text=""):
    print(text)
    REPORT.append(text)


def hit_rate(results, expect):
    """Top-K 中是否命中期望来源。"""
    sources = [d.metadata.get("source", "") for d in results]
    return 1 if any(expect in s for s in sources) else 0


def top1_correct(results, expect):
    """Top1 是否来自期望来源。"""
    if not results:
        return 0
    return 1 if expect in results[0].metadata.get("source", "") else 0


# ============================================================
# 准备：加载文档入库
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
print("BM25 索引构建完成\n")

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

for tc in TEST_CASES:
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
    vec_hits += v_hit; bm25_hits += b_hit; fused_hits += f_hit
    vec_top1 += v_t1; bm25_top1 += b_t1; fused_top1 += f_t1

    v_src = vec_docs[0].metadata.get("source", "?")[:12] if vec_docs else "-"
    b_src = bm25_docs[0].metadata.get("source", "?")[:12] if bm25_docs else "-"
    f_src = fused_docs[0].metadata.get("source", "?")[:12] if fused_docs else "-"
    log(f"| {q[:14]} | {expect[:10]} | {v_src} | {b_src} | {f_src} | {v_hit} | {b_hit} | {f_hit} |")

n = len(TEST_CASES)
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

# ============================================================
# 实验 2：重排前后对比
# ============================================================
log("## 实验 2：重排前后对比（RRF 融合 vs CrossEncoder 重排）")
log()
log("| 问题 | 重排前Top1 | 重排后Top1 | Top1变化 | 重排耗时 |")
log("|------|-----------|-----------|---------|---------|")

rerank_changes = 0
rerank_top1_correct = 0
total_rerank_time = 0

for tc in TEST_CASES:
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

    log(f"| {q[:14]} | {before_src} | {after_src} | {changed} | {rt*1000:.0f}ms |")

log()
log(f"**重排效果**：")
log(f"- Top1 顺序发生变化的题目：{rerank_changes}/{n}")
log(f"- 重排后 Top1 准确率：{rerank_top1_correct}/{n} = {rerank_top1_correct/n*100:.1f}%")
log(f"- 重排后 Top1 准确率 vs 混合检索 Top1：{rerank_top1_correct/n*100:.1f}% vs {fused_top1/n*100:.1f}%")
log(f"- 平均重排耗时：{total_rerank_time/n*1000:.0f}ms")
log()

# ============================================================
# 实验 3：缓存效果
# ============================================================
log("## 实验 3：缓存效果（LRU 精确缓存 + FAISS 语义缓存）")
log()

q0 = TEST_CASES[0]["q"]
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
    for tc in TEST_CASES:
        res = ret_tmp.retrieve(tc["q"], k=3)
        hit = hit_rate(res, tc["expect"])
        t1 = top1_correct(res, tc["expect"])
        if size == 300:
            results_300[tc["q"]] = (hit, t1, len(chunks_tmp))
        else:
            results_600[tc["q"]] = (hit, t1, len(chunks_tmp))

h300 = sum(v[0] for v in results_300.values())
h600 = sum(v[0] for v in results_600.values())
t300 = sum(v[1] for v in results_300.values())
t600 = sum(v[1] for v in results_600.values())
c300 = list(results_300.values())[0][2]
c600 = list(results_600.values())[0][2]

log(f"| 指标 | chunk_size=300 | chunk_size=600 |")
log(f"|------|---------------|---------------|")
log(f"| 切分片段数 | {c300} | {c600} |")
log(f"| 命中率（Top3） | {h300}/{n} = {h300/n*100:.1f}% | {h600}/{n} = {h600/n*100:.1f}% |")
log(f"| Top1 准确率 | {t300}/{n} = {t300/n*100:.1f}% | {t600}/{n} = {t600/n*100:.1f}% |")
log()
log("**结论**：chunk_size 较小时片段更细，命中率高但上下文可能不完整；较大时上下文完整但可能引入噪声。需根据文档类型权衡。")
log()

# ============================================================
# 写报告
# ============================================================
report_path = Path("experiments_report.md")
report_path.write_text("\n".join(REPORT), encoding="utf-8")
print("\n" + "=" * 60)
print(f"报告已生成：{report_path.resolve()}")
print("=" * 60)
