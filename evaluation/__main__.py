"""CLI 入口：python -m evaluation [--no-gate] [--report-dir PATH]。"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.runner import run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description="RAGAS 评估 + 质量门禁")
    parser.add_argument("--no-gate", action="store_true", help="仅评估出报告，不做门禁拦截")
    parser.add_argument("--report-dir", default="data/eval", help="报告输出目录")
    args = parser.parse_args()

    passed = run_evaluation(no_gate=args.no_gate, report_dir=args.report_dir)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
