"""
Testes de comportamento do ModelGuard (src/services/model_guard.py).
Verifica serialização FIFO, stats observáveis e integração com EventBus.
"""
import asyncio
import pytest

from src.services.event_bus import EventBus
from src.services.model_guard import ModelGuard, get_model_guard


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def guard(bus: EventBus) -> ModelGuard:
    """Instância limpa por teste com bus dedicado."""
    return ModelGuard(bus=bus)


# ---------------------------------------------------------------------------
# 1. Acquire / release básico
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acquire_e_release_basico(guard: ModelGuard) -> None:
    async with guard.acquire("ask_knowledge_base", kind="chat"):
        s = guard.stats()
        assert s["holder"]["tool"] == "ask_knowledge_base"
        assert s["holder"]["kind"] == "chat"

    s = guard.stats()
    assert s["holder"] is None


@pytest.mark.asyncio
async def test_stats_sem_holder_retorna_none(guard: ModelGuard) -> None:
    s = guard.stats()
    assert s["holder"] is None
    assert s["queue_depth"] == 0


# ---------------------------------------------------------------------------
# 2. Serialização — segunda task aguarda a primeira terminar
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_segunda_task_aguarda_primeira(guard: ModelGuard) -> None:
    order: list[str] = []

    async def tarefa(nome: str, duracao: float) -> None:
        async with guard.acquire(nome, kind="embed"):
            order.append(f"{nome}:start")
            await asyncio.sleep(duracao)
            order.append(f"{nome}:end")

    await asyncio.gather(
        tarefa("primeira", 0.05),
        tarefa("segunda", 0.01),
    )

    # As execuções devem ser serializadas — nunca intercaladas
    assert order.index("primeira:end") < order.index("segunda:start")


@pytest.mark.asyncio
async def test_serializa_cinco_tasks_concorrentes(guard: ModelGuard) -> None:
    active_simultaneously: list[int] = []
    counter = {"n": 0}

    async def tarefa(_: int) -> None:
        async with guard.acquire(f"tool_{_}", kind="embed"):
            counter["n"] += 1
            active_simultaneously.append(counter["n"])
            await asyncio.sleep(0.01)
            counter["n"] -= 1

    await asyncio.gather(*[tarefa(i) for i in range(5)])

    # Em nenhum momento mais de 1 task estava dentro do guard
    assert max(active_simultaneously) == 1


# ---------------------------------------------------------------------------
# 3. Stats — queue_depth e total_acquires
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_depth_durante_espera(guard: ModelGuard) -> None:
    depth_snapshot: list[int] = []

    async def ocupante() -> None:
        async with guard.acquire("ocupante", kind="embed"):
            await asyncio.sleep(0.1)

    async def entrante() -> None:
        # Entra na fila enquanto ocupante ainda segura o lock
        await asyncio.sleep(0.01)
        async with guard.acquire("entrante", kind="chat"):
            pass

    async def observador() -> None:
        # Lê após o entrante ter tido chance de entrar na fila
        await asyncio.sleep(0.04)
        depth_snapshot.append(guard.stats()["queue_depth"])

    await asyncio.gather(ocupante(), entrante(), observador())

    assert depth_snapshot[0] >= 1


@pytest.mark.asyncio
async def test_total_acquires_incrementa(guard: ModelGuard) -> None:
    for kind in ("embed", "chat", "vision"):
        async with guard.acquire("tool", kind=kind):
            pass

    assert guard.stats()["total_acquires"] == 3


# ---------------------------------------------------------------------------
# 4. Eventos do EventBus emitidos pelo guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emite_model_acquired_e_released(guard: ModelGuard, bus: EventBus) -> None:
    events: list[str] = []
    bus.subscribe("model.*", lambda p: events.append(p["event"]))

    async with guard.acquire("ask_knowledge_base", kind="chat"):
        pass

    assert "model.acquired" in events
    assert "model.released" in events


@pytest.mark.asyncio
async def test_emite_model_queued_quando_ha_espera(guard: ModelGuard, bus: EventBus) -> None:
    queued_events: list[dict] = []
    bus.subscribe("model.queued", lambda p: queued_events.append(p))

    async def ocupante() -> None:
        async with guard.acquire("ocupante", kind="embed"):
            await asyncio.sleep(0.05)

    async def entrante() -> None:
        await asyncio.sleep(0.01)
        async with guard.acquire("entrante", kind="chat"):
            pass

    await asyncio.gather(ocupante(), entrante())

    assert len(queued_events) >= 1
    assert queued_events[0]["tool"] == "entrante"


# ---------------------------------------------------------------------------
# 5. with_model_guard decorator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decorator_with_model_guard(bus: EventBus) -> None:
    from src.services.model_guard import with_model_guard

    guard = ModelGuard(bus=bus)
    calls: list[str] = []

    @with_model_guard(kind="embed", guard_instance=guard)
    async def minha_tool() -> str:
        calls.append("executou")
        return "ok"

    result = await minha_tool()

    assert result == "ok"
    assert calls == ["executou"]
    assert guard.stats()["total_acquires"] == 1


# ---------------------------------------------------------------------------
# 6. Singleton global
# ---------------------------------------------------------------------------

def test_get_model_guard_retorna_mesma_instancia() -> None:
    a = get_model_guard()
    b = get_model_guard()
    assert a is b


# ---------------------------------------------------------------------------
# 7. peek_next_kind lookahead
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_peek_next_kind(guard: ModelGuard) -> None:
    # Sem ninguém na fila, retorna None
    assert guard.peek_next_kind() is None

    async def ocupante():
        async with guard.acquire("ocupante", kind="embed"):
            await asyncio.sleep(0.05)
            # Durante a execução do ocupante, o entrante deve estar na fila
            assert guard.peek_next_kind() == "chat"

    async def entrante():
        await asyncio.sleep(0.01)
        async with guard.acquire("entrante", kind="chat"):
            pass

    await asyncio.gather(ocupante(), entrante())

    # Após liberar a fila inteira, retorna None
    assert guard.peek_next_kind() is None
