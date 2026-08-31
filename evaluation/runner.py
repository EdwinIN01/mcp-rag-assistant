"""评估执行器：构建样本 → 跑 RAGAS → 生成报告 → 质量门禁判定。

流程：
1. 从 experiments.py 导入测试集（正样本 20 / 负样本 5）
2. 对每题执行完整 RAG 管线（检索 + 生成），不依赖 FastAPI 服务，CI 可直接跑
3. 正样本组装 SingleTurnSample 交给 ragas.evaluate：
   - faithfulness        回答是否忠实于检索内容（反幻觉）
   - answer_relevancy    回答与问题的相关性
   - context_precision   检索上下文的精确率（排序质量）
   - context_recall      检索上下文对标准答案的覆盖率（召回质量）
4. 负样本用关键词模式判定拒绝率（知识库外问题应明确拒答）
5. 与 config.eval_thresholds 逐项比对，输出报告，低于阈值返回非零退出码
"""
import asyncio
import datetime
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import config

# ---------- 拒答模式（负样本判定） ----------
REJECT_PATTERNS = ["无法回答", "知识库中不", "未包含", "无法提供", "没有相关", "不包含", "无法找到"]


def _looks_like_rejection(answer: str) -> bool:
    return any(p in answer for p in REJECT_PATTERNS)


# ---------- RAG 管线（评估用，同步直连引擎） ----------

_retriever = None


def _get_retriever():
    """评估进程内复用同一检索器（reranker/BM25 只加载一次）。"""
    global _retriever
    if _retriever is None:
        from rag_engine.retriever import HybridRetriever
        from rag_engine.vectorstore import VectorStore

        _retriever = HybridRetriever(VectorStore())
    return _retriever


def _build_system_prompt() -> str:
    from api.services import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _run_rag_pipeline(question: str, k: int = 5) -> tuple[list[str], str]:
    """检索 + 生成，返回 (检索上下文列表, 生成的回答)。"""
    from openai import OpenAI

    retriever = _get_retriever()
    docs = retriever.retrieve(question, k)

    if not docs:
        return [], "知识库中未检索到相关内容。"

    contexts = [d.page_content for d in docs]
    reference_block = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
    user_msg = f"用户问题：{question}\n\n参考资料（来自知识库）：\n{reference_block}"

    if not config.llm_api_key:
        return contexts, f"（未配置 LLM API Key）\n\n{reference_block[:500]}"

    client = OpenAI(
        base_url=config.llm_api_base or None,
        api_key=config.llm_api_key,
    )
    resp = client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
    )
    return contexts, resp.choices[0].message.content


# ---------- RAGAS 评估 ----------

def _build_judge_llm():
    """评估 judge LLM：复用项目的 OpenAI 兼容配置（qwen-plus 等）。

    max_tokens=8192：faithfulness 的逐句判定 JSON 较长，
    qwen-plus 默认 3072 会被截断导致该题失败。
    """
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    client = AsyncOpenAI(
        base_url=config.llm_api_base or None,
        api_key=config.llm_api_key,
    )
    return llm_factory(
        model=config.llm_model, provider="openai", client=client, max_tokens=8192
    )


def _build_judge_embeddings():
    """answer_relevancy 所需 embeddings：复用项目本地 BGE Embedder（离线、零 API 成本）。

    ragas 0.4.x 的 HuggingFaceEmbeddings 缺少 embed_query/embed_documents 旧接口，
    这里自定义 wrapper 桥接到 rag_engine.Embedder 单例（模型只加载一次）。
    """
    from ragas.embeddings import BaseRagasEmbeddings
    from rag_engine.embedder import Embedder

    class _ProjectEmbeddings(BaseRagasEmbeddings):
        def embed_query(self, text: str) -> list[float]:
            return Embedder.embed_query(text)

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return Embedder.embed_documents(texts)

        async def aembed_query(self, text: str) -> list[float]:
            return await asyncio.to_thread(Embedder.embed_query, text)

        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
            return await asyncio.to_thread(Embedder.embed_documents, texts)

    return _ProjectEmbeddings()


def _run_ragas(samples: list) -> dict:
    """执行 RAGAS 评估，返回 {指标名: [逐题分数]}。"""
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    from ragas.run_config import RunConfig

    dataset = EvaluationDataset(samples)
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=_build_judge_llm(),
        embeddings=_build_judge_embeddings(),
        # 并发过高会触发 LLM API 限流 → 指标变 nan，降并发 + 保留重试
        run_config=RunConfig(max_workers=4, timeout=180, max_retries=10),
        show_progress=True,
    )
    # EvaluationResult → DataFrame（每行一题，每列一指标）
    df = result.to_pandas()
    return {m: df[m].tolist() for m in df.columns if df[m].dtype.kind == "f"}


# ---------- 主入口 ----------

def run_evaluation(no_gate: bool = False, report_dir: str = "data/eval") -> bool:
    """完整评估 + 门禁。返回 True 表示通过，False 表示被门禁拦截。"""
    from experiments import TEST_CASES

    positives = [tc for tc in TEST_CASES if tc["expect"] is not None]
    negatives = [tc for tc in TEST_CASES if tc["expect"] is None]

    print(f"[eval] 测试集：正样本 {len(positives)} 题（RAGAS 四指标）+ "
          f"负样本 {len(negatives)} 题（拒绝率）")
    if not config.llm_api_key:
        print("[eval][ERROR] 未配置 LLM_API_KEY，无法运行评估（judge 与生成都需要）")
        return False

    # 1. 跑 RAG 管线收集样本
    from ragas import SingleTurnSample

    samples: list[SingleTurnSample] = []
    per_case: list[dict] = []
    t0 = time.perf_counter()
    for i, tc in enumerate(positives, 1):
        contexts, answer = _run_rag_pipeline(tc["q"])
        samples.append(
            SingleTurnSample(
                user_input=tc["q"],
                retrieved_contexts=contexts,
                response=answer,
                reference=tc["answer"],
            )
        )
        per_case.append({"q": tc["q"], "expect": tc["expect"], "response": answer})
        print(f"[eval] ({i}/{len(positives)}) {tc['q']} → {len(contexts)} 个上下文")

    # 2. RAGAS 四指标
    print("[eval] 运行 RAGAS 评估（LLM-as-Judge，耗时视题量与模型而定）...")
    scores = asyncio.run(_run_ragas_async(samples))

    # 3. 负样本拒绝率
    rejected = 0
    neg_details: list[dict] = []
    for tc in negatives:
        _, answer = _run_rag_pipeline(tc["q"])
        ok = _looks_like_rejection(answer)
        rejected += ok
        neg_details.append({"q": tc["q"], "rejected": ok, "response": answer[:120]})
        print(f"[eval] 负样本 {'✓已拒答' if ok else '✗未拒答'}: {tc['q']}")
    rejection_rate = rejected / len(negatives) if negatives else 1.0

    # 4. 汇总各指标均值（忽略个别超时样本的 nan，避免单点毒化整体指标）
    metrics_summary = {}
    nan_counts: dict[str, int] = {}
    for m, values in scores.items():
        valid = [v for v in values if v is not None and v == v]  # v == v 过滤 nan
        nan_counts[m] = len(values) - len(valid)
        metrics_summary[m] = sum(valid) / len(valid) if valid else 0.0
    metrics_summary["rejection_rate"] = rejection_rate

    # 5. 生成报告
    report_path = _write_report(
        metrics_summary, scores, per_case, neg_details, nan_counts, report_dir
    )

    # 6. 门禁判定
    thresholds = config.eval_thresholds
    print("\n[gate] 质量门禁判定：")
    passed = True
    for metric, value in metrics_summary.items():
        threshold = thresholds.get(metric)
        if threshold is None:
            continue
        # nan 率超过 30% 视为评估本身不可信，同样拦截
        nan_rate = nan_counts.get(metric, 0) / max(len(scores.get(metric, [])), 1)
        ok = value >= threshold and nan_rate <= 0.3
        passed &= ok
        nan_note = f"，nan {nan_counts.get(metric, 0)} 题" if nan_counts.get(metric) else ""
        print(f"  {'PASS' if ok else 'FAIL'}  {metric:20s} {value:.4f} "
              f"(阈值 >= {threshold}{nan_note})")

    elapsed = time.perf_counter() - t0
    print(f"\n[eval] 完成，总耗时 {elapsed:.0f}s，报告：{report_path}")
    if not passed and not no_gate:
        print("[gate] ❌ 评估未达标，拦截本次变更")
    elif not passed:
        print("[gate] ⚠️ 评估未达标（--no-gate 模式，不拦截）")
    else:
        print("[gate] ✅ 全部指标达标")
    return passed


async def _run_ragas_async(samples: list) -> dict:
    """ragas.evaluate 需要 event loop，包一层避免在同步流程中嵌套 asyncio.run 冲突。"""
    return _run_ragas(samples)


def _write_report(
    metrics_summary: dict,
    scores: dict,
    per_case: list[dict],
    neg_details: list[dict],
    nan_counts: dict,
    report_dir: str,
) -> str:
    """输出 JSON 明细 + Markdown 摘要，返回 Markdown 路径。"""
    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    detail = {
        "timestamp": ts,
        "summary": metrics_summary,
        "thresholds": config.eval_thresholds,
        "nan_counts": nan_counts,
        "per_metric_scores": scores,
        "positive_cases": per_case,
        "negative_cases": neg_details,
    }

    def _clean(obj):
        """递归把 nan/None 分数转为 null（标准 JSON）。"""
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, float) and obj != obj:  # nan
            return None
        return obj

    (out_dir / f"eval_{ts}.json").write_text(
        json.dumps(_clean(detail), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# RAGAS 评估报告",
        "",
        f"- 时间：{ts}",
        f"- 正样本：{len(per_case)} 题（RAGAS 四指标）",
        f"- 负样本：{len(neg_details)} 题（拒绝率 {metrics_summary.get('rejection_rate', 0):.2%}）",
        "",
        "## 指标汇总",
        "",
        "| 指标 | 得分 | 阈值 | 判定 |",
        "|------|------|------|------|",
    ]
    for metric, value in metrics_summary.items():
        threshold = config.eval_thresholds.get(metric)
        verdict = "-" if threshold is None else ("PASS" if value >= threshold else "FAIL")
        th = "-" if threshold is None else f">= {threshold}"
        lines.append(f"| {metric} | {value:.4f} | {th} | {verdict} |")

    lines += ["", "## 逐题得分", "", "| 问题 | " + " | ".join(scores.keys()) + " |",
              "|" + "---|" * (len(scores) + 1)]
    for i, case in enumerate(per_case):
        row = [case["q"][:30]]
        for m in scores:
            v = scores[m][i] if i < len(scores[m]) else None
            row.append(f"{v:.3f}" if v is not None else "-")
        lines.append("| " + " | ".join(row) + " |")

    md_path = out_dir / f"eval_{ts}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(md_path)
