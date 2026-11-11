"""Print activation and retention from anonymous usage events over the last N days.

Usage: venv/bin/python scripts/product_report.py [--days 30]
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.services.product_events import product_summary  # noqa: E402


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30)
    days = parser.parse_args().days
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    db = SessionLocal()
    try:
        s = product_summary(db, since)
    finally:
        db.close()

    setup, retention, payday = s["setup"], s["retention"], s["payday_emails"]
    print(f"Pocketday usage, last {days} days\n")
    print(f"Setup: {setup['started']} started, {setup['finished']} finished ({_pct(setup['completion_rate'])})")
    print(f"  median {setup['median_minutes'] or 'n/a'} min, under 3 min: {_pct(setup['under_3_minutes_rate'])}")
    print(f"First number seen: {s['first_number_seen']}")
    print(f"Active in the last 14 days: {s['active_last_14_days']}")
    print(
        f"Came back in their second pay cycle: {retention['returned_in_second_cycle']} of "
        f"{retention['cohort']} ({_pct(retention['rate'])})"
    )
    print(f"Payday emails: {payday['sent']} sent, {payday['links_clicked']} links clicked ({_pct(payday['click_rate'])})")
    print(f"Alerts sent: {s['alerts_sent']}")
    print("\nAll events:")
    for name, count in s["events"].items():
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
