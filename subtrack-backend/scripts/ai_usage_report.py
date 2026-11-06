"""Print latency, error rate and cost for Claude calls over the last N days.

Usage: venv/bin/python scripts/ai_usage_report.py [--days 7]
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.services.ai_tracing import usage_summary  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7)
    days = parser.parse_args().days
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    db = SessionLocal()
    try:
        summary = usage_summary(db, since)
    finally:
        db.close()

    if not summary:
        print(f"No AI calls recorded in the last {days} days.")
        return
    print(f"AI calls in the last {days} days")
    for feature, entry in summary.items():
        print(
            f"\n{feature}: {entry['calls']} calls, "
            f"{entry['error_rate']:.0%} errors, "
            f"p50 {entry['p50_ms']} ms, p95 {entry['p95_ms']} ms, "
            f"${entry['cost_usd']:.4f} total"
        )
        if "requests" in entry:
            print(
                f"  per request ({entry['requests']}): "
                f"p50 {entry['request_p50_ms']} ms, p95 {entry['request_p95_ms']} ms, "
                f"${entry['cost_per_request_usd']:.5f} average"
            )


if __name__ == "__main__":
    main()
