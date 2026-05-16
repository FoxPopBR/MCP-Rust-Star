import datetime
import pytest
from dashboard.state_decider import decide_state

def test_offline_when_no_snapshot():
    state = decide_state(None)
    assert state["status"] == "offline"

def test_offline_when_stale():
    old_ts = (datetime.datetime.now() - datetime.timedelta(seconds=40)).isoformat()
    state = decide_state({"ts": old_ts})
    assert state["status"] == "offline"

def test_active_state():
    now_ts = datetime.datetime.now().isoformat()
    state = decide_state({"ts": now_ts, "activity": "active"})
    assert state["status"] == "active"
    assert state["spinner"] is True

def test_standby_state():
    now_ts = datetime.datetime.now().isoformat()
    state = decide_state({"ts": now_ts, "activity": "idle"})
    assert state["status"] == "standby"
    assert state["spinner"] is False

def test_error_state():
    now_ts = datetime.datetime.now().isoformat()
    state = decide_state({"ts": now_ts, "activity": "error"})
    assert state["status"] == "error"
    assert state["color"] == "#ef4444"
