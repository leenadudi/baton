"""MongoStore exercised against mongomock — same code path, no live MongoDB."""

import mongomock
import pytest

from app import store as store_mod


@pytest.fixture()
def mstore(monkeypatch):
    monkeypatch.setattr("pymongo.MongoClient", mongomock.MongoClient)
    return store_mod.MongoStore("mongodb://unused")


def test_user_token_roundtrip(mstore):
    doc = mstore.create_user("a@b.co", "Dr. A", "nightfloat")
    assert mstore.user_by_email("a@b.co")["id"] == doc["id"]
    token = mstore.create_token(doc["id"])
    assert mstore.user_for_token(token)["name"] == "Dr. A"
    mstore.revoke_token(token)
    assert mstore.user_for_token(token) is None
    with pytest.raises(store_mod.StoreError):
        mstore.create_user("a@b.co", "Dr. Dupe", "nightfloat")


def test_state_persists_across_reads(mstore):
    s = mstore.get_state("unit")
    s["owners"]["p1:x"] = "Dr. A"
    mstore.save_state("unit", s)
    assert mstore.get_state("unit")["owners"] == {"p1:x": "Dr. A"}
    assert mstore.get_state("session:z")["owners"] == {}
    mstore.reset_state("unit")
    assert mstore.get_state("unit")["owners"] == {}


def test_actions_filtered_by_scope_patient_doctor(mstore):
    mstore.record_action("unit", {"at": 2, "doctorId": "d1", "doctorName": "Dr. A",
                                  "patientId": "p1", "action": "clear",
                                  "target": "p1:blocker:b1", "text": "x"})
    mstore.record_action("session:g", {"at": 1, "doctorId": None,
                                       "doctorName": "Guest", "patientId": "p1",
                                       "action": "fill", "target": "y",
                                       "text": "y"})
    assert len(mstore.list_actions("unit")) == 1
    assert mstore.list_actions("unit", patient_id="p2") == []
    assert len(mstore.list_actions("unit", doctor_id="d1")) == 1
    assert mstore.list_actions("unit", doctor_id="d2") == []
    assert len(mstore.list_actions("session:g")) == 1
