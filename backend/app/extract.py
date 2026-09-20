"""Free-text note -> structured tags via the OpenAI API.

The model reads; the rule engine decides. Tags are post-validated against
TOPICS so the model can never introduce a topic or value the rules do not
know.
"""

import json
import logging
import os

from fastapi import HTTPException
from openai import AsyncOpenAI, OpenAIError

from app.extract_prompt import SYSTEM_PROMPT
from app.rules import TOPICS

log = logging.getLogger(__name__)

# (model, role, text) -> validated result; notes repeat across runs
_cache: dict[tuple[str, str | None, str], dict] = {}


async def extract(text: str, role: str | None = None) -> dict:
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    key = (model, role, text)
    if key in _cache:
        return dict(_cache[key])
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(503, "OPENAI_API_KEY not set")
    client = AsyncOpenAI()
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Author role: {role or 'unknown'}\n\nNote:\n{text}"},
            ],
        )
    except OpenAIError:
        # A single flaky/timed-out call must not take down a panel load that
        # gathers extract() across every note (see fhir_panel.load_fhir_patients).
        # Not cached: a transient failure shouldn't permanently blank a note.
        log.warning("OpenAI extraction call failed for role=%r", role, exc_info=True)
        return {"role": role, "tags": []}
    try:
        parsed = json.loads(resp.choices[0].message.content or "{}")
    except ValueError:
        parsed = {}
    seen = set()
    tags = []
    for tag in parsed.get("tags") or []:
        topic, value = tag.get("topic"), tag.get("value")
        if topic in TOPICS and value in TOPICS[topic]["values"] and topic not in seen:
            seen.add(topic)
            tags.append({"topic": topic, "value": value})
    result = {"role": role, "tags": tags}
    _cache[key] = dict(result)
    return result
