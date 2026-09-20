"""Demo state facade over app.store.

Signed-in clinicians share the "unit" scope, so one doctor's actions update
the panel every teammate sees; guests get an isolated "session:<id>" sandbox.
Persistence is MongoDB when MONGODB_URI is set, in-memory otherwise — see
app.store for the backend and docs/schema.md for the data model.
"""

import time

from app import store as _store


def fresh() -> dict:
    return _store.fresh()


def for_session(sid: str | None) -> dict:
    return _store.get_store().get_state(_store.session_scope(sid))


def for_scope(scope: str) -> dict:
    return _store.get_store().get_state(scope)


def save_scope(scope: str, s: dict) -> None:
    _store.get_store().save_state(scope, s)


def reset(scope: str) -> None:
    _store.get_store().reset_state(scope)


def reset_all() -> None:
    _store.get_store().reset_all()


def prune() -> None:
    _store.get_store().prune()


def log_act(s: dict, pid: str, text: str, by: str | None = None,
            by_id: str | None = None) -> None:
    s["log"].setdefault(pid, []).insert(
        0, {"at": time.time() * 1000, "text": text, "by": by, "byId": by_id})
