"""In-memory demo state, per browser session.

Each X-Session-Id header value gets an isolated state dict, so one judge's
clicks never change another judge's panel or brief. Callers that send no
header share the "default" bucket (keeps curl / old clients working).
Restarting the server (or POST /demo/reset for that session) clears state.
Sessions idle longer than SESSION_TTL_S are pruned to bound memory on the
free host.
"""

import time

DEFAULT_SESSION = "default"
SESSION_TTL_S = 6 * 60 * 60


def fresh() -> dict:
    return {"added": {}, "filled": {}, "cleared": {}, "escalated": {},
            "pendOwners": {}, "owners": {}, "log": {}, "nextSeq": 1000}


STATES: dict[str, dict] = {}
_SEEN: dict[str, float] = {}


def _prune() -> None:
    cutoff = time.time() - SESSION_TTL_S
    for sid, seen in list(_SEEN.items()):
        if seen < cutoff:
            STATES.pop(sid, None)
            _SEEN.pop(sid, None)


def for_session(sid: str | None) -> dict:
    """The state dict for one session id (DEFAULT_SESSION when absent)."""
    _prune()
    sid = sid or DEFAULT_SESSION
    _SEEN[sid] = time.time()
    return STATES.setdefault(sid, fresh())


def reset(sid: str | None = None) -> None:
    sid = sid or DEFAULT_SESSION
    STATES[sid] = fresh()
    _SEEN[sid] = time.time()


def reset_all() -> None:
    STATES.clear()
    _SEEN.clear()


def log_act(s: dict, pid: str, text: str) -> None:
    s["log"].setdefault(pid, []).insert(0, {"at": time.time() * 1000, "text": text})
