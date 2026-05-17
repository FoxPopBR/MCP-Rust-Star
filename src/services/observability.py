"""Endpoints HTTP de observabilidade (ADR-0019): /health, /events/recent, /events/stream, /metrics."""

from __future__ import annotations

import asyncio
import json as _json
import time
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.services.model_guard import get_model_guard

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from src.services.event_bus import EventBus
    from src.services.rag_service import RAGService

_SSE_POLL_INTERVAL = 0.5
_SSE_KEEPALIVE_INTERVAL = 15.0
_SSE_HISTORY_WINDOW_S = 60.0


def register_observability_routes(
    mcp: "FastMCP",
    rag: "RAGService",
    bus: "EventBus",
    start_time: float,
) -> None:
    """Registra /health, /events/recent, /events/stream e /metrics no FastMCP."""

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        ollama_ok = False
        db_ok = False
        try:
            result = rag.ollama.check_connection()
            ollama_ok = bool(result.get("connected", False))
        except Exception:
            pass
        try:
            rag.db.get_inventory_stats()
            db_ok = True
        except Exception:
            pass

        recent = bus.history(limit=1)
        last_event_at = recent[-1]["ts"] if recent else None

        return JSONResponse({
            "status": "ok" if (ollama_ok and db_ok) else "degraded",
            "uptime_s": round(time.time() - start_time, 1),
            "ollama": "ok" if ollama_ok else "error",
            "db": "ok" if db_ok else "error",
            "model_guard": get_model_guard().stats(),
            "last_event_at": last_event_at,
        })

    @mcp.custom_route("/events/recent", methods=["GET"])
    async def events_recent(request: Request) -> JSONResponse:
        limit = min(int(request.query_params.get("limit", 50)), 500)
        pattern = request.query_params.get("pattern", "*")
        events = bus.history(pattern=pattern, limit=limit)
        return JSONResponse({"events": events, "count": len(events)})

    @mcp.custom_route("/events/stream", methods=["GET"])
    async def events_stream(request: Request):
        from sse_starlette.sse import EventSourceResponse

        cutoff = time.time() - _SSE_HISTORY_WINDOW_S

        async def generator():
            # Envia histórico recente (última janela) ao conectar
            buffered = bus.history(limit=500)
            for ev in buffered:
                if ev["ts"] >= cutoff:
                    yield {"event": ev["event"], "data": _json.dumps(ev)}

            last_ts = time.time()
            last_keepalive = time.time()

            while True:
                if await request.is_disconnected():
                    break

                now = time.time()
                all_recent = bus.history(limit=500)
                new_events = [e for e in all_recent if e["ts"] > last_ts]

                for ev in new_events:
                    last_ts = max(last_ts, ev["ts"])
                    yield {"event": ev["event"], "data": _json.dumps(ev)}

                if now - last_keepalive >= _SSE_KEEPALIVE_INTERVAL:
                    yield {"comment": "keepalive"}
                    last_keepalive = now

                await asyncio.sleep(_SSE_POLL_INTERVAL)

        return EventSourceResponse(generator())

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics(request: Request) -> JSONResponse:
        all_events = bus.history(limit=500)
        tool_calls = sum(1 for e in all_events if e["event"] == "tool.invoked")
        embed_done = sum(1 for e in all_events if e["event"] == "embed.completed")
        rag_queries = sum(1 for e in all_events if e["event"] == "rag.query")
        guard_stats = get_model_guard().stats()

        return JSONResponse({
            "tool_calls_total": tool_calls,
            "embed_completed_total": embed_done,
            "rag_queries_total": rag_queries,
            "model_guard_queue_depth": guard_stats.get("queue_depth", 0),
            "events_in_buffer": len(all_events),
            "uptime_s": round(time.time() - start_time, 1),
        })
