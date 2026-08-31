"""RAGAS 评估框架：自动化质量评估 + CI 质量门禁（阶段 4）。

设计：
- 复用 experiments.py 的 25 题测试集（20 正样本 + 5 负样本）
- 正样本跑 RAGAS 四指标（faithfulness / answer_relevancy /
  context_precision / context_recall），judge LLM 走项目现有 LLM 配置
- 负样本跑拒绝率（回答含拒答模式即视为正确拒答）
- 任一指标低于 config.eval_thresholds 阈值 → exit code 1（CI 拦截）

运行：
    python -m evaluation               # 完整评估 + 门禁
    python -m evaluation --no-gate     # 仅评估出报告，不拦截
"""
from .runner import run_evaluation

__all__ = ["run_evaluation"]
