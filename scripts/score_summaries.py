#!/usr/bin/env python3
"""Score summary_kr quality against the rule-based eval harness.

Usage:
    python scripts/score_summaries.py path/to/items.json
    python scripts/score_summaries.py items.json --threshold 0.9
    python scripts/score_summaries.py items.json --json

Input is a JSON array of {title, summary_kr, ...} dicts (extra fields ignored,
so a captured DigestItem-shaped dump works as-is). Exits 1 if pass rate falls
below --threshold (default 1.0).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai_news_digest.eval import DigestScore, score_items
from ai_news_digest.eval.scorer import RULES


def _print_table(score: DigestScore) -> None:
    if not score.items:
        print("(no items)")
        return

    title_w = min(50, max(20, max(len(i.title) for i in score.items)))
    fmt = f"{{:>3}}  {{:<6}}  {{:>5}}  {{:<{title_w}}}  {{}}"
    print(fmt.format("#", "status", "sim", "title", "violations"))
    print("-" * (title_w + 40))

    for n, item in enumerate(score.items, 1):
        status = "OK" if item.passed else "FAIL"
        title = item.title if len(item.title) <= title_w else item.title[: title_w - 1] + "…"
        violations = ", ".join(str(v) for v in item.violations) or "-"
        print(fmt.format(n, status, f"{item.title_sim:.2f}", title, violations))

    print()
    print(f"Pass rate: {score.passed_count}/{score.total} ({score.pass_rate:.0%})")
    by_rule = score.violations_by_rule()
    print("By rule:  " + ", ".join(f"{r}={by_rule[r]}" for r in RULES))


def _print_json(score: DigestScore) -> None:
    out = {
        "total": score.total,
        "passed": score.passed_count,
        "pass_rate": score.pass_rate,
        "by_rule": score.violations_by_rule(),
        "items": [
            {
                "title": i.title,
                "summary_kr": i.summary_kr,
                "title_sim": i.title_sim,
                "passed": i.passed,
                "violations": [{"rule": v.rule, "detail": v.detail} for v in i.violations],
            }
            for i in score.items
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON file with array of items")
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="Required pass rate (0.0–1.0). Exit 1 if pass_rate is below this.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table.",
    )
    args = parser.parse_args(argv)

    raw = args.input.read_text(encoding="utf-8")
    items = json.loads(raw)
    if not isinstance(items, list):
        print(f"expected JSON array, got {type(items).__name__}", file=sys.stderr)
        return 2

    score = score_items(items)
    (_print_json if args.json else _print_table)(score)

    return 0 if score.pass_rate >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
