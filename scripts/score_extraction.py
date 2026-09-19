#!/usr/bin/env python3
"""Score extract() against the hand-written tags in DEMO_PATIENTS.

Usage:
    cd backend && OPENAI_API_KEY=... python ../scripts/score_extraction.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.demo_patients import DEMO_PATIENTS  # noqa: E402
from app.extract import extract  # noqa: E402


async def main() -> int:
    exact = 0
    total = 0
    tp = fp = fn = 0
    for p in DEMO_PATIENTS:
        for i, note in enumerate(p["notes"], 1):
            expected = {(t, v) for t, v in note.get("tags", [])}
            result = await extract(note["text"], role=note.get("role"))
            got = {(t["topic"], t["value"]) for t in result["tags"]}
            total += 1
            if got == expected:
                exact += 1
            else:
                print(f"DIFF {p['id']} note{i} ({note['role']}): {note['text'][:70]}")
                print(f"  expected: {sorted(expected)}")
                print(f"  got:      {sorted(got)}")
            tp += len(expected & got)
            fp += len(got - expected)
            fn += len(expected - got)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    print(f"\n{exact}/{total} notes exact match; "
          f"tags precision {precision:.2f}, recall {recall:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
