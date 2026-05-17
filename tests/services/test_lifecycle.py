"""Testes unitários para src/services/lifecycle.py (ADR-0018 / Fase 5)."""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.services.lifecycle import (
    PID_FILE,
    _check_port_free,
    drain_model_guard,
    remove_pid_file,
    setup_signal_handlers,
    startup_probes,
    write_pid_file,
)


# ──────────────────────────────────────────────────────────────────────────────
# PID file
# ──────────────────────────────────────────────────────────────────────────────

def test_write_pid_file_cria_arquivo(tmp_path):
    path = str(tmp_path / "server.pid")
    write_pid_file(path)
    assert os.path.exists(path)
    assert int(open(path).read()) == os.getpid()


def test_remove_pid_file_apaga_arquivo(tmp_path):
    path = str(tmp_path / "server.pid")
    open(path, "w").write("12345")
    remove_pid_file(path)
    assert not os.path.exists(path)


def test_remove_pid_file_tolerante_se_nao_existe(tmp_path):
    path = str(tmp_path / "nao_existe.pid")
    remove_pid_file(path)  # não deve lançar exceção


# ──────────────────────────────────────────────────────────────────────────────
# Port probe
# ──────────────────────────────────────────────────────────────────────────────

def test_check_port_free_com_porta_livre():
    # Usa porta efêmera: bind na 0 e descobre o número
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # Depois que o socket é fechado a porta está livre
    assert _check_port_free("127.0.0.1", port) is True


def test_check_port_free_com_porta_em_uso():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ocupado:
        ocupado.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen(1)
        port = ocupado.getsockname()[1]
        assert _check_port_free("127.0.0.1", port) is False


# ──────────────────────────────────────────────────────────────────────────────
# startup_probes
# ──────────────────────────────────────────────────────────────────────────────

def _make_rag_mock(ollama_connected=True, db_ok=True):
    rag = MagicMock()
    rag.ollama.check_connection.return_value = {"connected": ollama_connected}
    if db_ok:
        rag.db.get_inventory_stats.return_value = []
    else:
        rag.db.get_inventory_stats.side_effect = RuntimeError("DB indisponível")
    return rag


def _make_bus_mock():
    bus = MagicMock()
    return bus


def test_startup_probes_sucesso(tmp_path):
    """Todas as probes passam — emite server.starting e server.started."""
    rag = _make_rag_mock()
    bus = _make_bus_mock()

    # Porta efêmera livre
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    startup_probes(rag, bus, "127.0.0.1", port)

    calls = [c.args[0] for c in bus.emit.call_args_list]
    assert "server.starting" in calls
    assert "server.started" in calls


def test_startup_probes_falha_porta_em_uso():
    """HTTP com porta ocupada deve chamar sys.exit(1)."""
    rag = _make_rag_mock()
    bus = _make_bus_mock()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ocupado:
        ocupado.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen(1)
        port = ocupado.getsockname()[1]

        with pytest.raises(SystemExit) as exc:
            startup_probes(rag, bus, "127.0.0.1", port, transport="streamable-http")
        assert exc.value.code == 1


def test_startup_probes_stdio_bloqueado_se_http_ativo():
    """STDIO com porta ocupada (HTTP ativo) deve chamar sys.exit(1)."""
    rag = _make_rag_mock()
    bus = _make_bus_mock()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ocupado:
        ocupado.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen(1)
        port = ocupado.getsockname()[1]

        with pytest.raises(SystemExit) as exc:
            startup_probes(rag, bus, "127.0.0.1", port, transport="stdio")
        assert exc.value.code == 1


def test_startup_probes_stdio_ok_sem_http():
    """STDIO com porta livre (sem HTTP ativo) deve completar com sucesso."""
    rag = _make_rag_mock()
    bus = _make_bus_mock()

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    startup_probes(rag, bus, "127.0.0.1", port, transport="stdio")

    calls = [c.args[0] for c in bus.emit.call_args_list]
    assert "server.starting" in calls
    assert "server.started" in calls


def test_startup_probes_falha_ollama():
    """Ollama offline deve chamar sys.exit(1)."""
    rag = _make_rag_mock(ollama_connected=False)
    bus = _make_bus_mock()

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    with pytest.raises(SystemExit) as exc:
        startup_probes(rag, bus, "127.0.0.1", port)
    assert exc.value.code == 1


def test_startup_probes_falha_db():
    """PostgreSQL inacessível deve chamar sys.exit(1)."""
    rag = _make_rag_mock(db_ok=False)
    bus = _make_bus_mock()

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    with pytest.raises(SystemExit) as exc:
        startup_probes(rag, bus, "127.0.0.1", port)
    assert exc.value.code == 1


# ──────────────────────────────────────────────────────────────────────────────
# drain_model_guard
# ──────────────────────────────────────────────────────────────────────────────

def test_drain_model_guard_retorna_imediato_se_livre():
    """Se o ModelGuard não está sendo segurado, drain retorna imediatamente."""
    guard_mock = MagicMock()
    guard_mock.stats.return_value = {"holder": None}

    with patch("src.services.model_guard.get_model_guard", return_value=guard_mock):
        # deve retornar em < 1s
        start = time.monotonic()
        drain_model_guard(timeout_s=5.0)
        assert time.monotonic() - start < 1.0


def test_drain_model_guard_aguarda_liberacao():
    """Drain aguarda enquanto guard está segurado e retorna quando liberado."""
    guard_mock = MagicMock()
    call_count = [0]

    def _stats():
        call_count[0] += 1
        # Retorna held nas primeiras 3 chamadas, depois livre
        return {"holder": "task-1" if call_count[0] < 4 else None}

    guard_mock.stats.side_effect = _stats

    with patch("src.services.model_guard.get_model_guard", return_value=guard_mock):
        drain_model_guard(timeout_s=5.0)

    assert call_count[0] >= 4


def test_drain_model_guard_resiste_a_timeout():
    """Se nunca liberar, drain retorna após o timeout sem lançar exceção."""
    guard_mock = MagicMock()
    guard_mock.stats.return_value = {"holder": "task-ocupada"}

    with patch("src.services.model_guard.get_model_guard", return_value=guard_mock):
        start = time.monotonic()
        drain_model_guard(timeout_s=0.3)
        elapsed = time.monotonic() - start

    assert 0.3 <= elapsed < 1.0


# ──────────────────────────────────────────────────────────────────────────────
# setup_signal_handlers
# ──────────────────────────────────────────────────────────────────────────────

def test_setup_signal_handlers_registra_sigint():
    """Após setup, SIGINT deve chamar exit_fn antes de encerrar o processo.

    O handler usa os._exit(0); mockamos para capturar a chamada sem matar o processo.
    """
    called = []
    exit_fn = lambda: called.append(True)

    setup_signal_handlers(exit_fn)

    try:
        with patch("src.services.lifecycle.os._exit") as mock_exit:
            signal.raise_signal(signal.SIGINT)
        assert called == [True]
        mock_exit.assert_called_once_with(0)
    finally:
        signal.signal(signal.SIGINT, signal.default_int_handler)
