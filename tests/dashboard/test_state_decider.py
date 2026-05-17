"""Testes table-driven do decisor de estado.

Cobre a matriz de combinações (alive × activity × frescor) e a prioridade
offline > error > active > standby.
"""

import datetime
import pytest

from dashboard.state_decider import (
    STALE_THRESHOLD_SECONDS,
    decide_state,
)


def _fresh_ts() -> str:
    return datetime.datetime.now().isoformat()


def _stale_ts(seconds_old: float = STALE_THRESHOLD_SECONDS + 5) -> str:
    return (
        datetime.datetime.now() - datetime.timedelta(seconds=seconds_old)
    ).isoformat()


def _snap(alive: bool, activity: str, ts: str | None = None) -> dict:
    return {
        "ts": ts if ts is not None else _fresh_ts(),
        "server": {"alive": alive, "activity": activity},
    }


# ── Offline ───────────────────────────────────────────────────────────────────


def test_offline_when_snapshot_is_none():
    assert decide_state(None)["status"] == "offline"


def test_offline_when_snapshot_is_empty():
    assert decide_state({})["status"] == "offline"


def test_offline_when_ts_missing():
    snap = {"server": {"alive": True, "activity": "active"}}
    assert decide_state(snap)["status"] == "offline"


def test_offline_when_ts_malformed():
    snap = {"ts": "not-a-date", "server": {"alive": True, "activity": "active"}}
    assert decide_state(snap)["status"] == "offline"


def test_offline_when_stale():
    assert decide_state(_snap(True, "active", ts=_stale_ts()))["status"] == "offline"


def test_offline_when_not_alive_even_if_fresh():
    assert decide_state(_snap(False, "active"))["status"] == "offline"


def test_offline_when_server_key_missing():
    snap = {"ts": _fresh_ts()}
    assert decide_state(snap)["status"] == "offline"


# ── Error ─────────────────────────────────────────────────────────────────────


def test_error_when_activity_error():
    state = decide_state(_snap(True, "error"))
    assert state["status"] == "error"
    assert state["color"] == "#ef4444"


def test_error_overrides_active_visually():
    # Server vivo, fresco, mas com activity=error → vence sobre active.
    snap = _snap(True, "error")
    snap["server"]["activity"] = "error"
    assert decide_state(snap)["status"] == "error"


# ── Active ────────────────────────────────────────────────────────────────────


def test_active_when_activity_active():
    state = decide_state(_snap(True, "active"))
    assert state["status"] == "active"
    assert state["color"] == "#22c55e"


# ── Standby ───────────────────────────────────────────────────────────────────


def test_standby_when_activity_idle():
    state = decide_state(_snap(True, "idle"))
    assert state["status"] == "standby"
    assert state["color"] == "#eab308"


def test_standby_when_activity_missing_defaults_to_idle():
    snap = {"ts": _fresh_ts(), "server": {"alive": True}}
    assert decide_state(snap)["status"] == "standby"


# ── Prioridade: offline > error ───────────────────────────────────────────────


def test_stale_beats_error():
    # ts stale com activity=error → vira offline, não fica em error.
    snap = _snap(True, "error", ts=_stale_ts())
    assert decide_state(snap)["status"] == "offline"


def test_not_alive_beats_error():
    assert decide_state(_snap(False, "error"))["status"] == "offline"


# ── Estrutura do retorno ─────────────────────────────────────────────────────


@pytest.mark.parametrize("activity", ["idle", "active", "error"])
def test_return_has_required_keys(activity):
    state = decide_state(_snap(True, activity))
    assert set(state.keys()) == {"status", "label", "color"}
    assert state["color"].startswith("#")
    assert state["label"]


def test_spinner_field_removed_from_decider():
    # spinner agora é responsabilidade do fetcher.is_fetching, não do decider.
    state = decide_state(_snap(True, "active"))
    assert "spinner" not in state
