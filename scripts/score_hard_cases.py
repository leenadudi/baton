#!/usr/bin/env python3
"""Score extract() against the hand-labeled hard-case eval sets in eval/.

Reported separately per source file (never blended into one number) per
extraction_context.md: the prototype notes and their tags were written
together, so a high score there mostly shows the pipeline works, not that
it generalizes. These sets exist to measure generalization.

Usage:
    cd backend && OPENAI_API_KEY=... python ../scripts/score_hard_cases.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.extract import extract  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
SOURCES = ["synthetic_edge_cases.json", "mtsamples_candidates.json"]


class _ApiFailureDetector(logging.Handler):
    """extract() degrades an OpenAI failure to {"tags": []} - indistinguishable
    from a genuine "no tags apply" result on any negative test case, which
    would silently inflate the score. Watches the warning extract() already
    logs on that path (added for exactly this kind of visibility) so a failed
    call can be excluded from scoring instead of counted as correct."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.failed = False

    def emit(self, record):
        self.failed = True


_detector = _ApiFailureDetector()
logging.getLogger("app.extract").addHandler(_detector)


async def score_file(path: Path) -> bool:
    data = json.loads(path.read_text())
    items = [i for i in data.get("items", []) if i.get("expected") is not None]
    skipped = len(data.get("items", [])) - len(items)
    if not items:
        note = " (not labeled yet)" if skipped else " (no items)"
        print(f"{path.name}: 0 labeled items{note}, skipping")
        return True

    exact = 0
    api_failures = 0
    tp = fp = fn = 0
    for item in items:
        expected = {(t, v) for t, v in item["expected"]}
        _detector.failed = False
        result = await extract(item["text"], role=item.get("role"))
        if _detector.failed:
            api_failures += 1
            print(f"SKIP {item['id']}: OpenAI call failed, excluded from score "
                  "(not counted as correct or incorrect)")
            continue
        got = {(t["topic"], t["value"]) for t in result["tags"]}
        if got == expected:
            exact += 1
        else:
            missed = expected - got
            invented = got - expected
            print(f"DIFF {item['id']} ({item.get('role')}): {item['text'][:70]}")
            if item.get("trap"):
                print(f"  trap: {item['trap']}")
            if missed:
                print(f"  missed:   {sorted(missed)}")
            if invented:
                print(f"  invented: {sorted(invented)}")
        tp += len(expected & got)
        fp += len(got - expected)
        fn += len(expected - got)

    scored = len(items) - api_failures
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    skip_note = f" ({skipped} unlabeled skipped)" if skipped else ""
    fail_note = f" ({api_failures} excluded: OpenAI call failed)" if api_failures else ""
    print(f"\n{path.name}: {exact}/{scored} exact match; "
          f"tags precision {precision:.2f}, recall {recall:.2f}{skip_note}{fail_note}")
    return api_failures == 0


async def main() -> int:
    ok = True
    for name in SOURCES:
        path = EVAL_DIR / name
        if not path.exists():
            print(f"{name}: not found, skipping")
            continue
        ok = await score_file(path) and ok
        print()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
