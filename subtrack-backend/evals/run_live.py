"""Run every eval case against Claude and compare the score with the baseline.

Usage: venv/bin/python -m evals.run_live [--report path] [--update-baseline]

Each case runs on a fresh in-memory database, so no real data is used. Exits
with status 1 when the pass rate drops more than the allowed margin below
evals/baseline.json, once a baseline has been recorded.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "eval-only")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from evals.graders import describe, grade  # noqa: E402
from evals.harness import load_cases, run_case, seed, utc_now  # noqa: E402

BASELINE_PATH = Path(__file__).with_name("baseline.json")
# Claude's answers vary between runs, so allow a small drop before failing.
ALLOWED_DROP = 0.05


def run_one(case: dict) -> dict:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        seed(db, utc_now())
        transcript = run_case(db, case["question"])
        grades = grade(transcript, case)
    except Exception as exc:  # noqa: BLE001 - a crashed case is a failed case, not a crashed run
        return {"id": case["id"], "category": case["category"], "passed": False,
                "grades": {}, "error": type(exc).__name__}
    finally:
        db.close()
        engine.dispose()
    return {
        "id": case["id"],
        "category": case["category"],
        "passed": all(g.passed for g in grades),
        "grades": {g.name: g.passed for g in grades},
        "detail": describe(grades),
        "tools": [call.name for call in transcript.tool_calls],
        "answer": transcript.answer,
    }


def summarise(results: list[dict]) -> dict:
    by_category: dict[str, list[bool]] = defaultdict(list)
    by_grader: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        by_category[result["category"]].append(result["passed"])
        for name, passed in result["grades"].items():
            by_grader[name].append(passed)

    def rate(values: list[bool]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    return {
        "pass_rate": rate([r["passed"] for r in results]),
        "cases": len(results),
        "by_category": {k: rate(v) for k, v in sorted(by_category.items())},
        "by_grader": {k: rate(v) for k, v in sorted(by_grader.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, help="write full results as JSON here")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    results = [run_one(case) for case in load_cases()]
    summary = summarise(results)
    if args.report:
        args.report.write_text(json.dumps({"summary": summary, "results": results}, indent=2))

    print(f"Pass rate: {summary['pass_rate']:.0%} of {summary['cases']} cases")
    for group in ("by_category", "by_grader"):
        print("  " + ", ".join(f"{k} {v:.0%}" for k, v in summary[group].items()))
    for result in results:
        if not result["passed"]:
            print(f"  FAIL {result['id']}: {result.get('error') or result['detail']}")

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"Baseline updated to {summary['pass_rate']:.0%}")
        return 0
    if not BASELINE_PATH.exists():
        print("No baseline yet; run with --update-baseline and commit evals/baseline.json.")
        return 0
    baseline = json.loads(BASELINE_PATH.read_text())["pass_rate"]
    if summary["pass_rate"] < baseline - ALLOWED_DROP:
        print(f"Regression: {summary['pass_rate']:.0%} is below the {baseline:.0%} baseline")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
