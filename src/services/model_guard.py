"""
ModelGuard — serialização global de operações que tocam Ollama (ADR-0016).

Garante que apenas uma operação de modelo (embed, chat, vision) execute
por vez, usando asyncio.Lock FIFO. Emite eventos model.* no EventBus.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from functools import wraps
from typing import Any, Callable

from src.services.event_bus import EventBus, get_event_bus

logger = logging.getLogger(__name__)

Kind = str  # "embed" | "chat" | "vision"


class ModelGuard:
    def __init__(self, bus: EventBus | None = None) -> None:
        self._lock = asyncio.Lock()
        self._bus = bus or get_event_bus()
        self._holder: dict | None = None
        self._queue: list[dict] = []
        self._total_acquires: int = 0

    # ------------------------------------------------------------------
    # Acquire context manager
    # ------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def acquire(self, tool_name: str, kind: Kind):
        """Context manager que serializa acesso ao Ollama.

        Emite model.queued se já houver um holder, model.acquired ao entrar
        e model.released ao sair.
        """
        enqueued_at = time.time()

        if self._lock.locked():
            entry = {"tool": tool_name, "kind": kind, "enqueued_at": enqueued_at}
            self._queue.append(entry)
            self._bus.emit("model.queued", {
                "tool": tool_name,
                "kind": kind,
                "depth_at_enqueue": len(self._queue),
                "event": "model.queued",
            })
            try:
                await self._lock.acquire()
            finally:
                if entry in self._queue:
                    self._queue.remove(entry)
        else:
            await self._lock.acquire()

        acquired_at = time.time()
        waited_ms = (acquired_at - enqueued_at) * 1000
        self._holder = {"tool": tool_name, "kind": kind, "started_at": acquired_at}
        self._total_acquires += 1

        self._bus.emit("model.acquired", {
            "tool": tool_name,
            "kind": kind,
            "waited_ms": round(waited_ms, 1),
            "event": "model.acquired",
        })

        try:
            yield self
        finally:
            held_ms = (time.time() - acquired_at) * 1000
            self._holder = None
            self._lock.release()
            self._bus.emit("model.released", {
                "tool": tool_name,
                "kind": kind,
                "held_ms": round(held_ms, 1),
                "event": "model.released",
            })

    # ------------------------------------------------------------------
    # Observabilidade
    # ------------------------------------------------------------------

    def peek_next_kind(self) -> Kind | None:
        """Retorna o tipo (kind) do próximo item na fila de espera, se houver."""
        if self._queue:
            return self._queue[0]["kind"]
        return None

    def stats(self) -> dict:
        return {
            "holder": dict(self._holder) if self._holder else None,
            "queue_depth": len(self._queue),
            "queue": [dict(e) for e in self._queue],
            "total_acquires": self._total_acquires,
        }


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def with_model_guard(kind: Kind, guard_instance: ModelGuard | None = None):
    """Decorator que envolve uma corrotina assíncrona com o ModelGuard.

    Uso:
        @with_model_guard(kind="embed")
        async def index_directory(...): ...

    Em testes, passe guard_instance explicitamente para controlar o estado.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            guard = guard_instance or get_model_guard()
            async with guard.acquire(func.__name__, kind=kind):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_guard: ModelGuard | None = None


def get_model_guard() -> ModelGuard:
    global _guard
    if _guard is None:
        _guard = ModelGuard()
    return _guard
