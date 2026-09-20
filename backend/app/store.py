"""Users, auth tokens, demo state, and the audit trail.

MongoDB (Atlas) when MONGODB_URI is set; otherwise an in-memory store so the
demo, tests, and a cold Render boot keep working with no external service.

State is keyed by scope: signed-in clinicians share UNIT_SCOPE so one doctor's
actions are visible to the whole team; guests get an isolated "session:<id>"
sandbox. Every mutation also writes an actions record (doctor, patient, time)
that backs the patient/doctor activity searches.
"""

import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timezone

UNIT_SCOPE = "unit"
SESSION_SCOPE_PREFIX = "session:"
SESSION_TTL_S = 6 * 60 * 60
MIN_PASSWORD_LEN = 6


def fresh() -> dict:
    return {"added": {}, "filled": {}, "cleared": {}, "escalated": {},
            "pendOwners": {}, "owners": {}, "log": {}, "nextSeq": 1000}


def _hash_pw(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), 60_000).hex()


def _public(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"]}


def session_scope(sid: str | None) -> str:
    # Cap header length so a caller cannot mint arbitrarily large scope keys.
    return SESSION_SCOPE_PREFIX + (sid or "default")[:128]


class StoreError(Exception):
    """Expected store failure; main.py maps it to an HTTP error."""


def _matches(a: dict, patient_id: str | None, doctor_id: str | None) -> bool:
    return (patient_id is None or a["patientId"] == patient_id) and \
           (doctor_id is None or a["doctorId"] == doctor_id)


class MemoryStore:
    kind = "memory"

    def __init__(self) -> None:
        self._users: dict[str, dict] = {}
        self._emails: dict[str, str] = {}
        self._tokens: dict[str, str] = {}
        self._states: dict[str, dict] = {}
        self._seen: dict[str, float] = {}
        self._actions: dict[str, list] = {}

    # --- demo state ---
    def get_state(self, scope: str) -> dict:
        self._seen[scope] = time.time()
        return self._states.setdefault(scope, fresh())

    def save_state(self, scope: str, s: dict) -> None:
        self._states[scope] = s

    def reset_state(self, scope: str) -> None:
        self._states[scope] = fresh()
        self._actions[scope] = []

    def prune(self) -> None:
        cutoff = time.time() - SESSION_TTL_S
        for scope, seen in list(self._seen.items()):
            if scope != UNIT_SCOPE and seen < cutoff:
                self._states.pop(scope, None)
                self._actions.pop(scope, None)
                self._seen.pop(scope, None)

    # --- audit trail ---
    def record_action(self, scope: str, action: dict) -> None:
        self._actions.setdefault(scope, []).insert(0, action)

    def list_actions(self, scope: str, patient_id: str | None = None,
                     doctor_id: str | None = None, limit: int = 200) -> list:
        acts = [a for a in self._actions.get(scope, [])
                if _matches(a, patient_id, doctor_id)]
        return acts[:limit]

    # --- users + tokens ---
    def create_user(self, email: str, name: str, password: str) -> dict:
        if email in self._emails:
            raise StoreError("an account already exists for that email")
        salt = secrets.token_hex(16)
        u = {"id": secrets.token_hex(8), "email": email, "name": name,
             "salt": salt, "pwHash": _hash_pw(password, salt),
             "createdAt": int(time.time() * 1000)}
        self._users[u["id"]] = u
        self._emails[email] = u["id"]
        return _public(u)

    def user_by_email(self, email: str) -> dict | None:
        uid = self._emails.get(email)
        return self._users.get(uid) if uid else None

    def user_by_id(self, uid: str) -> dict | None:
        return self._users.get(uid)

    def check_password(self, u: dict, password: str) -> bool:
        return hmac.compare_digest(u["pwHash"], _hash_pw(password, u["salt"]))

    def list_doctors(self) -> list:
        return [{"id": u["id"], "name": u["name"]} for u in self._users.values()]

    def create_token(self, uid: str) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = uid
        return token

    def user_for_token(self, token: str) -> dict | None:
        uid = self._tokens.get(token)
        u = self._users.get(uid) if uid else None
        return _public(u) if u else None

    def revoke_token(self, token: str) -> None:
        self._tokens.pop(token, None)

    def reset_all(self) -> None:
        self.__init__()


class MongoStore:
    kind = "mongo"

    def __init__(self, uri: str) -> None:
        from pymongo import ASCENDING, DESCENDING, MongoClient
        from pymongo.errors import DuplicateKeyError
        self._dup = DuplicateKeyError
        self._client = MongoClient(uri, serverSelectionTimeoutMS=4000)
        self._client.admin.command("ping")
        db = self._client["baton"]
        self._users = db["users"]
        self._tokens = db["tokens"]
        self._states = db["states"]
        self._actions = db["actions"]
        self._users.create_index("email", unique=True)
        self._actions.create_index([("scope", ASCENDING), ("patientId", ASCENDING)])
        self._actions.create_index([("scope", ASCENDING), ("doctorId", ASCENDING)])
        self._actions.create_index([("scope", ASCENDING), ("at", DESCENDING)])
        self._tokens.create_index("createdAt",
                                  expireAfterSeconds=7 * 24 * 60 * 60)

    # --- demo state ---
    def get_state(self, scope: str) -> dict:
        doc = self._states.find_one({"_id": scope})
        return {**fresh(), **doc["data"]} if doc else fresh()

    def save_state(self, scope: str, s: dict) -> None:
        self._states.replace_one(
            {"_id": scope},
            {"data": s, "updatedAt": int(time.time() * 1000)},
            upsert=True)

    def reset_state(self, scope: str) -> None:
        self._states.delete_one({"_id": scope})
        self._actions.delete_many({"scope": scope})

    def prune(self) -> None:
        self._states.delete_many(
            {"_id": {"$regex": f"^{SESSION_SCOPE_PREFIX}"},
             "updatedAt": {"$lt": int((time.time() - SESSION_TTL_S) * 1000)}})

    # --- audit trail ---
    def record_action(self, scope: str, action: dict) -> None:
        self._actions.insert_one({"scope": scope, **action})

    def list_actions(self, scope: str, patient_id: str | None = None,
                     doctor_id: str | None = None, limit: int = 200) -> list:
        q: dict = {"scope": scope}
        if patient_id:
            q["patientId"] = patient_id
        if doctor_id:
            q["doctorId"] = doctor_id
        return [{k: v for k, v in a.items() if k != "_id"}
                for a in self._actions.find(q).sort("at", -1).limit(limit)]

    # --- users + tokens ---
    def create_user(self, email: str, name: str, password: str) -> dict:
        salt = secrets.token_hex(16)
        u = {"_id": secrets.token_hex(8), "email": email, "name": name,
             "salt": salt, "pwHash": _hash_pw(password, salt),
             "createdAt": int(time.time() * 1000)}
        try:
            self._users.insert_one(u)
        except self._dup:
            raise StoreError("an account already exists for that email")
        return {"id": u["_id"], "name": name, "email": email}

    def user_by_email(self, email: str) -> dict | None:
        u = self._users.find_one({"email": email})
        return {**u, "id": u["_id"]} if u else None

    def user_by_id(self, uid: str) -> dict | None:
        u = self._users.find_one({"_id": uid})
        return {**u, "id": u["_id"]} if u else None

    def check_password(self, u: dict, password: str) -> bool:
        return hmac.compare_digest(u["pwHash"], _hash_pw(password, u["salt"]))

    def list_doctors(self) -> list:
        return [{"id": u["_id"], "name": u["name"]}
                for u in self._users.find({}, {"email": 0})]

    def create_token(self, uid: str) -> str:
        token = secrets.token_urlsafe(32)
        # TTL index needs a BSON datetime, not epoch ms.
        self._tokens.insert_one({"_id": token, "userId": uid,
                                 "createdAt": datetime.now(timezone.utc)})
        return token

    def user_for_token(self, token: str) -> dict | None:
        doc = self._tokens.find_one({"_id": token})
        if not doc:
            return None
        u = self._users.find_one({"_id": doc["userId"]})
        return {"id": u["_id"], "name": u["name"], "email": u["email"]} if u else None

    def revoke_token(self, token: str) -> None:
        self._tokens.delete_one({"_id": token})

    def reset_all(self) -> None:
        for coll in (self._users, self._tokens, self._states, self._actions):
            coll.delete_many({})


_STORE = None


def get_store():
    """Singleton store: Mongo when configured, memory otherwise."""
    global _STORE
    if _STORE is None:
        uri = os.environ.get("MONGODB_URI")
        if uri:
            try:
                _STORE = MongoStore(uri)
            except Exception as exc:  # unreachable/bad URI -> keep demo alive
                print(f"MongoStore unavailable ({exc}); using in-memory store")
                _STORE = MemoryStore()
        else:
            _STORE = MemoryStore()
    return _STORE
