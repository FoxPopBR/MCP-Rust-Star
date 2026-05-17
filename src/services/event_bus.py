"""
EventBus in-process singleton para pub/sub de eventos do servidor.

Garantias (ADR-0017):
- Wildcard subscriptions: "embed.*" captura todos os sub-eventos de embed.
- emit() é síncrono; handlers assíncronos são agendados via asyncio.create_task.
- emit_async() aguarda todos os handlers (sync e async) — use em shutdown.
- Erros em handlers são logados e isolados; nunca derrubam outros handlers.
- Ring buffer de 500 eventos para history() e o futuro endpoint /events/recent.
"""
from __future__ import annotations

import asyncio
import fnmatch
import inspect
import logging
import time
from collections import deque
from typing import Any, Callable

logger = logging.getLogger(__name__)

_RING_BUFFER_SIZE = 500

HandlerFn = Callable[[dict], Any]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[int, HandlerFn]]] = {}
        self._counter: int = 0
        self._buffer: deque[dict] = deque(maxlen=_RING_BUFFER_SIZE)

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, pattern: str, handler: HandlerFn) -> int:
        """Registra handler para eventos que casam com pattern (suporta * e ?).

        Retorna um token opaco para uso em unsubscribe().
        """
        self._counter += 1
        token = self._counter
        self._handlers.setdefault(pattern, []).append((token, handler))
        return token

    def unsubscribe(self, token: int) -> None:
        """Remove o handler identificado pelo token."""
        for pattern, entries in self._handlers.items():
            self._handlers[pattern] = [(t, h) for t, h in entries if t != token]

    # ------------------------------------------------------------------
    # Emit
    # ------------------------------------------------------------------

    def emit(self, event: str, payload: dict) -> None:
        """Emite evento de forma síncrona.

        Handlers síncronos são chamados imediatamente.
        Handlers assíncronos são agendados em asyncio.create_task (fire-and-forget).
        """
        self._record(event, payload)
        for handler in self._matching_handlers(event):
            self._invoke_sync(handler, payload, event)

    async def emit_async(self, event: str, payload: dict) -> None:
        """Emite evento e aguarda todos os handlers — síncronos e assíncronos."""
        self._record(event, payload)
        tasks: list[asyncio.Task] = []
        for handler in self._matching_handlers(event):
            if inspect.iscoroutinefunction(handler):
                tasks.append(asyncio.create_task(self._safe_async(handler, payload, event)))
            else:
                self._invoke_sync_no_schedule(handler, payload, event)
        if tasks:
            await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def history(self, pattern: str = "*", limit: int = 100) -> list[dict]:
        """Retorna os últimos `limit` eventos que casam com pattern."""
        matched = [e for e in self._buffer if fnmatch.fnmatch(e["event"], pattern)]
        return matched[-limit:]

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _matching_handlers(self, event: str) -> list[HandlerFn]:
        result: list[HandlerFn] = []
        for pattern, entries in self._handlers.items():
            if fnmatch.fnmatch(event, pattern):
                result.extend(h for _, h in entries)
        return result

    def _record(self, event: str, payload: dict) -> None:
        self._buffer.append({"event": event, "payload": payload, "ts": time.time()})

    def _invoke_sync(self, handler: HandlerFn, payload: dict, event: str) -> None:
        if inspect.iscoroutinefunction(handler):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._safe_async(handler, payload, event))
            except RuntimeError:
                pass
        else:
            self._invoke_sync_no_schedule(handler, payload, event)

    def _invoke_sync_no_schedule(self, handler: HandlerFn, payload: dict, event: str) -> None:
        try:
            handler(payload)
        except Exception:
            logger.error("EventBus: erro no handler de '%s' (%s)", event, handler, exc_info=True)

    async def _safe_async(self, handler: HandlerFn, payload: dict, event: str) -> None:
        try:
            await handler(payload)
        except Exception:
            logger.error("EventBus: erro no handler async de '%s' (%s)", event, handler, exc_info=True)


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
