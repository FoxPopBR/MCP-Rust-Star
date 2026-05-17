"""
Testes de comportamento do EventBus (src/services/event_bus.py).
Estratégia TDD: cada bloco de teste descreve UM comportamento observável
via interface pública — sem inspecionar internos.
"""
import asyncio
import pytest

from src.services.event_bus import EventBus, get_event_bus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def bus() -> EventBus:
    """Instância limpa por teste — NÃO usa o singleton global."""
    return EventBus()


# ---------------------------------------------------------------------------
# 1. Subscribe + emit básico (síncrono)
# ---------------------------------------------------------------------------

def test_handler_chamado_apos_emit(bus: EventBus) -> None:
    received: list[dict] = []

    bus.subscribe("tool.invoked", lambda payload: received.append(payload))
    bus.emit("tool.invoked", {"tool": "ask_knowledge_base"})

    assert len(received) == 1
    assert received[0]["tool"] == "ask_knowledge_base"


def test_multiplos_handlers_no_mesmo_evento(bus: EventBus) -> None:
    calls: list[str] = []

    bus.subscribe("tool.completed", lambda _: calls.append("A"))
    bus.subscribe("tool.completed", lambda _: calls.append("B"))
    bus.emit("tool.completed", {})

    assert set(calls) == {"A", "B"}


def test_handler_nao_chamado_em_evento_diferente(bus: EventBus) -> None:
    received: list[dict] = []

    bus.subscribe("rag.query.received", lambda p: received.append(p))
    bus.emit("tool.invoked", {"tool": "index_file"})

    assert received == []


# ---------------------------------------------------------------------------
# 2. Wildcard subscriptions
# ---------------------------------------------------------------------------

def test_wildcard_captura_subevento(bus: EventBus) -> None:
    received: list[str] = []

    bus.subscribe("embed.*", lambda p: received.append(p.get("event", "")))
    bus.emit("embed.file.processed", {"event": "embed.file.processed"})
    bus.emit("embed.batch.completed", {"event": "embed.batch.completed"})
    bus.emit("tool.invoked", {"event": "tool.invoked"})

    assert "embed.file.processed" in received
    assert "embed.batch.completed" in received
    assert "tool.invoked" not in received


def test_wildcard_server_estrela(bus: EventBus) -> None:
    received: list[str] = []

    bus.subscribe("server.*", lambda p: received.append(p["e"]))
    bus.emit("server.starting", {"e": "starting"})
    bus.emit("server.started", {"e": "started"})
    bus.emit("server.health.tick", {"e": "health"})

    assert received == ["starting", "started", "health"]


# ---------------------------------------------------------------------------
# 3. Unsubscribe
# ---------------------------------------------------------------------------

def test_unsubscribe_impede_chamadas_futuras(bus: EventBus) -> None:
    received: list[dict] = []

    token = bus.subscribe("model.acquired", lambda p: received.append(p))
    bus.emit("model.acquired", {"first": True})
    bus.unsubscribe(token)
    bus.emit("model.acquired", {"second": True})

    assert len(received) == 1
    assert received[0]["first"] is True


# ---------------------------------------------------------------------------
# 4. Isolamento de erros — handler com bug não derruba os demais
# ---------------------------------------------------------------------------

def test_handler_com_excecao_nao_cancela_outros(bus: EventBus) -> None:
    survived: list[bool] = []

    def handler_bugado(_: dict) -> None:
        raise RuntimeError("bug proposital")

    bus.subscribe("tool.failed", handler_bugado)
    bus.subscribe("tool.failed", lambda _: survived.append(True))
    bus.emit("tool.failed", {})

    assert survived == [True]


# ---------------------------------------------------------------------------
# 5. Ring buffer (history)
# ---------------------------------------------------------------------------

def test_history_retorna_eventos_na_ordem_cronologica(bus: EventBus) -> None:
    for i in range(5):
        bus.emit("index.source.added", {"i": i})

    hist = bus.history("index.*", limit=10)
    values = [e["payload"]["i"] for e in hist]
    assert values == [0, 1, 2, 3, 4]


def test_history_respeita_limite(bus: EventBus) -> None:
    for i in range(20):
        bus.emit("rag.query.answered", {"i": i})

    hist = bus.history("rag.*", limit=5)
    assert len(hist) == 5
    # Os últimos 5
    assert [e["payload"]["i"] for e in hist] == [15, 16, 17, 18, 19]


def test_history_filtra_por_padrao(bus: EventBus) -> None:
    bus.emit("embed.file.processed", {"src": "embed"})
    bus.emit("rag.query.received", {"src": "rag"})
    bus.emit("embed.batch.completed", {"src": "embed2"})

    hist = bus.history("embed.*")
    assert all(e["event"].startswith("embed.") for e in hist)
    assert len(hist) == 2


def test_ring_buffer_descarta_eventos_mais_antigos(bus: EventBus) -> None:
    """Buffer de 500: ao estourar, o mais antigo é descartado."""
    for i in range(510):
        bus.emit("tool.invoked", {"i": i})

    hist = bus.history("tool.*", limit=500)
    # O evento mais antigo no buffer deve ter i >= 10
    oldest_i = hist[0]["payload"]["i"]
    assert oldest_i >= 10


# ---------------------------------------------------------------------------
# 6. emit_async — aguarda handlers assíncronos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emit_async_aguarda_handler_async(bus: EventBus) -> None:
    results: list[str] = []

    async def async_handler(payload: dict) -> None:
        await asyncio.sleep(0)
        results.append(payload["msg"])

    bus.subscribe("server.started", async_handler)
    await bus.emit_async("server.started", {"msg": "ok"})

    assert results == ["ok"]


@pytest.mark.asyncio
async def test_emit_async_erro_em_handler_nao_propaga(bus: EventBus) -> None:
    survived: list[bool] = []

    async def handler_bugado(_: dict) -> None:
        raise ValueError("async bug")

    bus.subscribe("server.stopping", handler_bugado)
    bus.subscribe("server.stopping", lambda _: survived.append(True))

    await bus.emit_async("server.stopping", {})

    assert survived == [True]


# ---------------------------------------------------------------------------
# 7. Singleton global
# ---------------------------------------------------------------------------

def test_get_event_bus_retorna_mesma_instancia() -> None:
    a = get_event_bus()
    b = get_event_bus()
    assert a is b
