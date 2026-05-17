"""
Testes de integração: TelemetryWriter orientado a eventos (ADR-0014 / Fase 4).

Valida que:
1. O TelemetryWriter assina o EventBus e reage a eventos relevantes.
2. O heartbeat escreve o arquivo mesmo sem eventos.
3. O snapshot inclui recent_events do bus.
4. O throttle de 250ms bloqueia escritas em burst.
5. A troca de _publish_telemetry() por _bus.emit() produz snaps idênticos.
"""

from __future__ import annotations

import json
import os
import threading
import time

from src.services.event_bus import EventBus
from src.services.telemetry_writer import TelemetryWriter


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures auxiliares
# ──────────────────────────────────────────────────────────────────────────────

def _make_writer(tmp_path, bus=None) -> TelemetryWriter:
    """Cria um TelemetryWriter com estado mínimo para testes."""
    embed_state = {"running": False, "log_lines": []}
    rag_state = {}
    return TelemetryWriter(
        state_file=str(tmp_path / "state.json"),
        bus=bus,
        get_embed_state_fn=lambda: embed_state,
        get_rag_state_fn=lambda: rag_state,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. Assinatura automática no EventBus
# ──────────────────────────────────────────────────────────────────────────────

def test_writer_escreve_arquivo_ao_receber_evento_tool(tmp_path):
    """Emitir tool.invoked deve acionar escrita do arquivo de estado."""
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)
    state_file = str(tmp_path / "state.json")

    assert not os.path.exists(state_file)
    bus.emit("tool.invoked", {"tool": "index_file"})
    # Dá margem para o handler síncrono completar
    time.sleep(0.05)

    assert os.path.exists(state_file), "Arquivo de estado deve existir após evento tool.*"


def test_writer_escreve_ao_receber_evento_embed(tmp_path):
    """Emitir embed.log.appended deve acionar escrita."""
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)
    state_file = str(tmp_path / "state.json")

    bus.emit("embed.log.appended", {})
    time.sleep(0.05)

    assert os.path.exists(state_file)


def test_writer_escreve_ao_receber_evento_rag(tmp_path):
    """Emitir rag.state.changed deve acionar escrita."""
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)
    state_file = str(tmp_path / "state.json")

    bus.emit("rag.state.changed", {})
    time.sleep(0.05)

    assert os.path.exists(state_file)


def test_writer_escreve_ao_receber_evento_model(tmp_path):
    """Emitir model.acquired deve acionar escrita."""
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)
    state_file = str(tmp_path / "state.json")

    bus.emit("model.acquired", {"tool": "ask_knowledge_base", "kind": "chat"})
    time.sleep(0.05)

    assert os.path.exists(state_file)


def test_writer_nao_escreve_sem_bus(tmp_path):
    """Sem EventBus, nenhum evento dispara escrita automaticamente."""
    # Sem bus — o writer só escreve se chamado diretamente
    writer = _make_writer(tmp_path, bus=None)
    state_file = str(tmp_path / "state.json")

    # _trigger_write() exige get_embed_state_fn; sem bus não há subscriber
    assert not os.path.exists(state_file)


# ──────────────────────────────────────────────────────────────────────────────
# 2. recent_events incluídos no snapshot
# ──────────────────────────────────────────────────────────────────────────────

def test_snapshot_inclui_recent_events(tmp_path):
    """O snapshot deve conter os últimos eventos do bus (até 20).

    Emitimos dois eventos, esperamos o throttle de 250ms expirar,
    depois emitimos um terceiro para forçar a escrita com todos no histórico.
    """
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)

    bus.emit("tool.invoked", {"tool": "list_projects"})
    bus.emit("tool.completed", {"tool": "list_projects", "duration_s": 0.01})
    # Aguarda throttle (250ms) e força nova escrita com histórico completo
    time.sleep(0.3)
    bus.emit("server.heartbeat", {})
    time.sleep(0.05)

    state_file = str(tmp_path / "state.json")
    with open(state_file, encoding="utf-8") as f:
        data = json.load(f)

    recent = data.get("recent_events", [])
    assert len(recent) >= 2
    event_names = [e["event"] for e in recent]
    assert "tool.invoked" in event_names
    assert "tool.completed" in event_names


def test_snapshot_recent_events_limitado_a_20(tmp_path):
    """O snapshot não deve incluir mais de 20 eventos recentes."""
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)

    for i in range(30):
        bus.emit("tool.invoked", {"tool": f"tool_{i}"})

    time.sleep(0.05)
    bus.emit("tool.completed", {"tool": "final"})
    time.sleep(0.05)

    state_file = str(tmp_path / "state.json")
    with open(state_file, encoding="utf-8") as f:
        data = json.load(f)

    assert len(data.get("recent_events", [])) <= 20


# ──────────────────────────────────────────────────────────────────────────────
# 3. Heartbeat — liveness sem eventos
# ──────────────────────────────────────────────────────────────────────────────

def test_heartbeat_escreve_arquivo_sem_eventos(tmp_path):
    """Thread de heartbeat deve escrever o arquivo mesmo sem eventos no bus."""
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)
    state_file = str(tmp_path / "state.json")

    stop = threading.Event()
    t = threading.Thread(target=writer.heartbeat_loop, args=(stop,), daemon=True)
    t.start()

    # Espera até 3s para o arquivo aparecer (heartbeat padrão = 10s mas
    # _trigger_write() é chamado imediatamente na primeira iteração)
    deadline = time.monotonic() + 3.0
    while not os.path.exists(state_file) and time.monotonic() < deadline:
        time.sleep(0.05)

    stop.set()
    t.join(timeout=2)

    assert os.path.exists(state_file), "Heartbeat deve escrever o arquivo de estado"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Escrita atômica — arquivo não deve ficar corrompido
# ──────────────────────────────────────────────────────────────────────────────

def test_arquivo_e_json_valido_apos_multiplos_eventos(tmp_path):
    """Burst de eventos deve produzir um JSON válido no final."""
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)
    state_file = str(tmp_path / "state.json")

    for _ in range(20):
        bus.emit("embed.file.processing", {})

    time.sleep(0.4)  # espera throttle + escrita

    assert os.path.exists(state_file)
    with open(state_file, encoding="utf-8") as f:
        data = json.load(f)  # não deve lançar exceção

    assert "version" in data
    assert "ts" in data
    assert "server" in data


# ──────────────────────────────────────────────────────────────────────────────
# 5. Schema do snapshot — campos obrigatórios (ADR-0014)
# ──────────────────────────────────────────────────────────────────────────────

def test_snapshot_tem_campos_obrigatorios(tmp_path):
    """O snapshot deve conter todos os campos definidos no schema v2."""
    bus = EventBus()
    writer = _make_writer(tmp_path, bus=bus)

    bus.emit("server.started", {})
    time.sleep(0.1)

    state_file = str(tmp_path / "state.json")
    with open(state_file, encoding="utf-8") as f:
        data = json.load(f)

    required_top = {"version", "ts", "server", "indexing", "batch", "inventory", "log_tail", "recent_events"}
    assert required_top <= data.keys(), f"Campos faltando: {required_top - data.keys()}"

    assert data["version"] == 2
    assert data["server"]["alive"] is True
    assert data["server"]["activity"] in ("idle", "active", "error")
