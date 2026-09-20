"""Advisory AI suggestions for issues (`/suggest/*`).

The model reads, the rules decide: every suggestion is a draft a clinician
confirms; nothing is applied automatically and no suggestion picks a conflict
winner (AGENTS.md). All outputs are post-validated before they leave here.
"""

import json
import logging
import os

from fastapi import HTTPException
from openai import AsyncOpenAI, OpenAIError

from app import rules
from app.suggest_prompts import (
    CLARIFY_SYSTEM, FIELD_SYSTEM, HUDDLE_SYSTEM, OWNER_SYSTEM)

log = logging.getLogger(__name__)

# Mirrors frontend/src/data/chart.js OWNERS — keep in sync.
OWNERS = ["Charge RN", "Hospitalist", "Case Management", "Pharmacy",
          "Social Work", "PT/OT", "Unit Clerk"]


async def _ask(system: str, user: str) -> dict:
    """One JSON-mode chat completion. 503 if no key; {} on OpenAIError."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(503, "OPENAI_API_KEY not set")
    client = AsyncOpenAI()
    try:
        resp = await client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
    except OpenAIError:
        log.warning("OpenAI suggestion call failed", exc_info=True)
        return {}
    try:
        parsed = json.loads(resp.choices[0].message.content or "{}")
    except ValueError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _note_line(note: dict) -> str:
    return f"{note.get('role', '?')}, {note.get('author', '?')}, " \
           f"{note.get('h', '?')}h ago: {note.get('text', '')}"


async def clarify(issue: dict, patient: dict) -> dict:
    """Draft a neutral message asking the note authors which instruction stands."""
    topic = issue.get("topic", "")
    label = rules.TOPICS.get(topic, {}).get("label", topic)
    lines = [f"Patient: {patient.get('name')} (Rm {patient.get('room')})",
             f"Topic with conflicting instructions: {label}", ""]
    for value, notes in (issue.get("vals") or {}).items():
        lines.append(f"Instruction: {value}")
        for n in notes:
            lines.append(f"  - {_note_line(n)}")
        lines.append("")
    res = await _ask(CLARIFY_SYSTEM, "\n".join(lines))
    return {"advisory": True, "message": res.get("message") or ""}


async def owner(issue: dict, patient: dict, allowed: list[str]) -> dict:
    """Suggest which team role should own a blocker or pending result."""
    lines = [f"Patient: {patient.get('name')} (Rm {patient.get('room')})",
             f"Issue: {issue.get('title')}",
             f"Detail: {issue.get('sub')}",
             f"Why it matters: {issue.get('why')}"]
    if issue.get("type") == "blocker":
        b = next((b for b in patient.get("blockers", [])
                  if b["id"] == issue.get("bid")), None)
        if b:
            lines.append(f"Category: {b.get('cat')}; waiting on "
                         f"{b.get('waitingOn') or 'unknown'}; "
                         f"{'blocks discharge' if b.get('blocks') else 'not blocking'}; "
                         f"open {b.get('ageH')}h")
    elif (issue.get("fix") or {}).get("kind") == "pending":
        lines.append(f"Pending result: {issue['fix']['name']}")
    care_team = (patient.get("info") or {}).get("careTeam")
    if care_team:
        lines.append(f"Care team: {care_team}")
    lines.append(f"Allowed owners: {', '.join(allowed)}")
    res = await _ask(OWNER_SYSTEM, "\n".join(lines))
    pick = res.get("owner")
    if pick not in allowed:
        pick = None
    return {"advisory": True, "owner": pick, "reason": res.get("reason") or ""}


async def field(issue: dict, patient: dict) -> dict:
    """Find a missing handoff field's value stated in an existing note."""
    key = (issue.get("fix") or {}).get("key")
    label = next((f["label"] for f in rules.FIELDS if f["key"] == key), key)
    notes = patient.get("notes", [])
    lines = [f"Handoff field missing: {label}", "", "Chart notes:"]
    for i, n in enumerate(notes):
        lines.append(f"[{i}] {_note_line(n)}")
    res = await _ask(FIELD_SYSTEM, "\n".join(lines))
    value, source = res.get("value"), None
    idx, quote = res.get("noteIndex"), res.get("quote")
    if value is not None and isinstance(idx, int) and 0 <= idx < len(notes):
        note = notes[idx]
        # The quote, if returned, must appear verbatim in that note — otherwise
        # we can't trust the attribution and drop the whole suggestion.
        if not quote or quote.lower() in (note.get("text") or "").lower():
            source = {"role": note.get("role"), "author": note.get("author"),
                      "h": note.get("h"), "text": note.get("text"),
                      "source": note.get("source")}
    if source is None:
        value = None
    return {"advisory": True, "value": value, "quote": quote, "source": source}


async def huddle(brief: str) -> dict:
    """Rewrite the shift brief as a ~30-second spoken huddle script."""
    res = await _ask(HUDDLE_SYSTEM, brief)
    return {"advisory": True, "script": res.get("script") or ""}
