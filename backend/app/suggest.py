"""Coordination next-step suggestions for issues.

The model suggests the *process* step — who should own it, what to verify,
when to escalate — never a clinical answer, and never a winner when
instructions conflict. When OPENAI_API_KEY is unset (or the call fails) a
deterministic rule-based suggestion is returned instead, so the feature
demos offline and never hard-fails mid-demo.
"""

import hashlib
import json
import logging
import os

from openai import AsyncOpenAI, OpenAIError

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Baton, a shift-handoff coordination assistant embedded in a
hospital unit dashboard. Given one coordination issue on a synthetic patient
chart, suggest the single most useful NEXT COORDINATION STEP.

Hard rules — these are product safety boundaries, not style:
- Suggest process only: who should own it, what fact to verify, who to notify,
  when to escalate. NEVER recommend treatment, medication, doses, or any
  clinical action.
- For conflicting instructions, NEVER pick a winner. Suggest who should
  reconcile (e.g. the attending) and what to verify before anyone follows
  either instruction.
- One or two sentences of plain language. No markdown, no bullets, no caveats.
- Use the concrete roles and names in the issue when possible."""

# fingerprint -> {"text", "source"}; issues change rarely, suggestions repeat.
_cache: dict[str, dict] = {}


def _fingerprint(issue: dict) -> str:
    """Hash the fields a suggestion depends on, so a changed issue (new note,
    new owner, escalation) produces a fresh suggestion instead of a stale one."""
    stable = {
        "type": issue["type"], "title": issue["title"], "sub": issue.get("sub"),
        "sev": issue["sev"], "owner": issue.get("owner") or "",
        "escalated": bool(issue.get("escalated")),
        "vals": {v: [(n.get("role"), n.get("author")) for n in ns]
                 for v, ns in (issue.get("vals") or {}).items()},
    }
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True).encode()).hexdigest()


def _fallback(issue: dict) -> str:
    """Deterministic coordination suggestion from the issue's own fields."""
    if issue["type"] == "conflict":
        roles = sorted({n.get("role") for ns in (issue.get("vals") or {}).values()
                        for n in ns if n.get("role")})
        who = " and ".join(roles) if roles else "each team"
        return (f"Have the attending reconcile this one — ask {who} to confirm "
                "which instruction was last carried out before anyone follows "
                "either. Baton flags conflicts; it does not pick the winner.")
    if issue["type"] == "handoff":
        if (issue.get("fix") or {}).get("kind") == "pending":
            return ("Assign a named owner for this pending result before shift "
                    "change — unowned follow-ups are the ones that come back "
                    "abnormal and go unseen.")
        return ("Fill this field before the next shift takes over — it is "
                "required for a complete handoff.")
    # blocker
    if issue.get("escalated"):
        return ("Escalation is logged — confirm the charge nurse or bed "
                "coordinator has seen it, and note the expected resolution "
                "time in the handoff.")
    return ("Assign an owner and confirm with whoever it is waiting on; if it "
            "has not moved by the next check-in, escalate to the charge nurse.")


def _context(issue: dict, p: dict) -> str:
    ctx = {
        "patient": {"name": p.get("name"), "dx": p.get("dx"),
                    "dischargeInH": p.get("dischargeInH")},
        "issue": {"type": issue["type"], "severity": issue["sev"],
                  "title": issue["title"], "detail": issue.get("sub"),
                  "owner": issue.get("owner") or "unassigned"},
    }
    if issue["type"] == "conflict":
        ctx["issue"]["assertions"] = [
            {"role": n.get("role"), "value": v,
             "note": (n.get("text") or "")[:300]}
            for v, ns in (issue.get("vals") or {}).items() for n in ns]
    return json.dumps(ctx)


async def for_issue(issue: dict, p: dict) -> dict:
    """Return {"text", "source"} — source is the model name or "rules"."""
    fp = _fingerprint(issue)
    if fp in _cache:
        return dict(_cache[fp])
    fallback = {"text": _fallback(issue), "source": "rules"}
    if not os.environ.get("OPENAI_API_KEY"):
        _cache[fp] = fallback
        return dict(fallback)
    client = AsyncOpenAI()
    try:
        resp = await client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.3,
            max_tokens=120,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _context(issue, p)},
            ],
        )
        text = (resp.choices[0].message.content or "").strip().strip('"')
    except OpenAIError:
        # Suggestions are a nice-to-have overlay; a flaky call must not 500 the
        # card. Serve the rule-based fallback rather than an empty drawer.
        log.warning("OpenAI suggestion call failed", exc_info=True)
        text = ""
    if not text:
        _cache[fp] = fallback
        return dict(fallback)
    result = {"text": text[:500],
              "source": os.environ.get("OPENAI_MODEL", "gpt-4o-mini")}
    _cache[fp] = result
    return dict(result)
