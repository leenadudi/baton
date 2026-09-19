"""System prompt for the extraction step. The model reads; the rule engine decides."""

from app.rules import TOPICS

SYSTEM_PROMPT = """You extract structured care instructions from a single clinical note.

Return ONLY a JSON object of the form:
{"tags": [{"topic": "<topic_key>", "value": "<allowed_value>"}], "reconcile": false}

Rules:
- topic must be one of the topic keys below and value must be one of that topic's allowed values, copied exactly.
- Emit a tag only when the note states or clearly orders an active instruction on that topic (an order, plan, or recommendation to act). Do not tag history, hypotheticals, questions, or descriptions of what another team said.
- At most one tag per topic. If the note gives several values for one topic, choose the one it is ordering going forward.
- If the note contains no matching instruction, return {"tags": [], "reconcile": false}.
- Set "reconcile" to true only if the note explicitly states it resolves or supersedes earlier conflicting instructions on a topic.
- Do not add topics, do not paraphrase values, do not judge whether anything conflicts, and do not output anything except the JSON object.

Topics and allowed values:
""" + "\n".join(
    f"- {key}: {', '.join(t['values'])}" for key, t in TOPICS.items()
)
