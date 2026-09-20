"""In-memory demo state, mirroring the prototype's persisted `state` object.

Demo mutations live here only; restarting the server (or POST /demo/reset)
clears them.
"""

import time


def fresh() -> dict:
    return {"added": {}, "filled": {}, "cleared": {}, "escalated": {},
            "pendOwners": {}, "owners": {}, "log": {}, "nextSeq": 1000}


STATE = fresh()


def reset() -> None:
    STATE.clear()
    STATE.update(fresh())


def log_act(pid: str, text: str, resolved: bool = True) -> None:
    """resolved=False for entries that are ongoing or failed, not completed
    (e.g. escalating a blocker raises its urgency, it doesn't close it) —
    the Completed tab filters on this so open/failed work doesn't read as done."""
    STATE["log"].setdefault(pid, []).insert(
        0, {"at": time.time() * 1000, "text": text, "resolved": resolved})
