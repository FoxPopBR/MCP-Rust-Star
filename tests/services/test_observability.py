"""Testes para src/services/observability.py (ADR-0019 / Fase 6)."""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from src.services.event_bus import EventBus
from src.services.observability import register_observability_routes


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_rag(ollama_ok=True, db_ok=True):
    rag = MagicMock()
    rag.ollama.check_connection.return_value = {"connected": ollama_ok}
    if db_ok:
        rag.db.get_inventory_stats.return_value = []
    else:
        rag.db.get_inventory_stats.side_effect = RuntimeError("DB down")
    return rag


def _make_mcp_stub(bus, rag, start_time):
    """Cria um app Starlette mínimo simulando como FastMCP integra custom_route."""
    routes_store: list = []

    class _FakeMCP:
        def custom_route(self, path, methods, **kw):
            def decorator(fn):
                routes_store.append(Route(path, endpoint=fn, methods=methods))
                return fn
            return decorator

    fake_mcp = _FakeMCP()
    register_observability_routes(fake_mcp, rag, bus, start_time)
    return Starlette(routes=routes_store)


# ─── /health ──────────────────────────────────────────────────────────────────

def test_health_ok():
    bus = EventBus()
    rag = _make_rag()
    start = time.time() - 10.0
    app = _make_mcp_stub(bus, rag, start)

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {"holder": None, "queue_depth": 0}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["ollama"] == "ok"
    assert data["db"] == "ok"
    assert data["uptime_s"] >= 10.0


def test_health_degraded_ollama():
    bus = EventBus()
    rag = _make_rag(ollama_ok=False)
    app = _make_mcp_stub(bus, rag, time.time())

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {"holder": None, "queue_depth": 0}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app) as client:
            resp = client.get("/health")

    data = resp.json()
    assert data["status"] == "degraded"
    assert data["ollama"] == "error"
    assert data["db"] == "ok"


def test_health_degraded_db():
    bus = EventBus()
    rag = _make_rag(db_ok=False)
    app = _make_mcp_stub(bus, rag, time.time())

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {"holder": None, "queue_depth": 0}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app) as client:
            resp = client.get("/health")

    data = resp.json()
    assert data["status"] == "degraded"
    assert data["db"] == "error"


def test_health_last_event_at_none_quando_buffer_vazio():
    bus = EventBus()
    rag = _make_rag()
    app = _make_mcp_stub(bus, rag, time.time())

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app) as client:
            resp = client.get("/health")

    assert resp.json()["last_event_at"] is None


def test_health_last_event_at_preenchido():
    bus = EventBus()
    bus.emit("server.started", {})
    rag = _make_rag()
    app = _make_mcp_stub(bus, rag, time.time())

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app) as client:
            resp = client.get("/health")

    assert resp.json()["last_event_at"] is not None


# ─── /events/recent ───────────────────────────────────────────────────────────

def test_events_recent_retorna_lista():
    bus = EventBus()
    bus.emit("tool.invoked", {"tool": "ask"})
    bus.emit("embed.completed", {"file": "x.rs"})
    rag = _make_rag()
    app = _make_mcp_stub(bus, rag, time.time())

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app) as client:
            resp = client.get("/events/recent")

    data = resp.json()
    assert resp.status_code == 200
    assert data["count"] == 2
    assert len(data["events"]) == 2


def test_events_recent_respeita_limit():
    bus = EventBus()
    for i in range(20):
        bus.emit("tool.invoked", {"n": i})
    rag = _make_rag()
    app = _make_mcp_stub(bus, rag, time.time())

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app) as client:
            resp = client.get("/events/recent?limit=5")

    data = resp.json()
    assert data["count"] == 5


def test_events_recent_filtra_por_pattern():
    bus = EventBus()
    bus.emit("tool.invoked", {"tool": "ask"})
    bus.emit("embed.completed", {"file": "x.rs"})
    bus.emit("tool.completed", {"tool": "ask"})
    rag = _make_rag()
    app = _make_mcp_stub(bus, rag, time.time())

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app) as client:
            resp = client.get("/events/recent?pattern=tool.*")

    data = resp.json()
    assert data["count"] == 2
    assert all(e["event"].startswith("tool.") for e in data["events"])


# ─── /metrics ─────────────────────────────────────────────────────────────────

def test_metrics_contagem_basica():
    bus = EventBus()
    bus.emit("tool.invoked", {})
    bus.emit("tool.invoked", {})
    bus.emit("embed.completed", {})
    bus.emit("rag.query", {})
    rag = _make_rag()
    app = _make_mcp_stub(bus, rag, time.time() - 5)

    guard_mock = MagicMock()
    guard_mock.stats.return_value = {"queue_depth": 3}

    with patch("src.services.observability.get_model_guard", return_value=guard_mock):
        with TestClient(app) as client:
            resp = client.get("/metrics")

    data = resp.json()
    assert resp.status_code == 200
    assert data["tool_calls_total"] == 2
    assert data["embed_completed_total"] == 1
    assert data["rag_queries_total"] == 1
    assert data["model_guard_queue_depth"] == 3
    assert data["events_in_buffer"] == 4
    assert data["uptime_s"] >= 5.0
