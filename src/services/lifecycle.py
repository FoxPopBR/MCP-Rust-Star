"""Lifecycle robusto: startup probes, PID file e graceful shutdown (ADR-0018)."""

from __future__ import annotations

import os
import signal
import socket
import sys
import time
from typing import TYPE_CHECKING

from tools.logger import logger

if TYPE_CHECKING:
    from src.services.event_bus import EventBus

PID_FILE = os.path.join("data", "server.pid")
DRAIN_TIMEOUT_SECONDS = 5.0


# ─── PID file ─────────────────────────────────────────────────────────────────

def write_pid_file(path: str = PID_FILE) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        logger.debug(f"Lifecycle: PID {os.getpid()} escrito em {path}")
    except OSError as e:
        logger.warning(f"Lifecycle: não foi possível escrever PID file: {e}")


def remove_pid_file(path: str = PID_FILE) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.debug(f"Lifecycle: PID file {path} removido.")
    except OSError:
        pass


# ─── Startup probes ───────────────────────────────────────────────────────────

def _check_port_free(host: str, port: int) -> bool:
    """Retorna True se nenhum servidor está escutando na porta (connect-based)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def startup_probes(
    rag, bus: "EventBus", host: str, port: int, transport: str = "streamable-http"
) -> None:
    """Verifica pré-condições antes de iniciar o servidor.

    Emite server.starting antes das probes e server.started após sucesso.
    Chama sys.exit(1) em fail-fast se qualquer probe falhar.

    Probe de porta (transport-aware):
    - HTTP: porta deve estar LIVRE para o bind do uvicorn.
    - STDIO: porta deve estar LIVRE, sinalizando que nenhum servidor HTTP está ativo.
             Rodar STDIO com HTTP ativo corromperia o canal stdout do MCP.
    """
    bus.emit("server.starting", {"transport": transport, "host": host, "port": port})

    # Probe 1: porta (semântica depende do transporte)
    port_free = _check_port_free(host, port)
    if transport == "stdio":
        if not port_free:
            logger.critical(
                f"Lifecycle: servidor HTTP já está ativo em {host}:{port} — "
                "não é permitido iniciar em modo STDIO simultaneamente. "
                "Encerre o servidor HTTP primeiro (scripts/stop_server.bat)."
            )
            sys.exit(1)
        logger.info(f"Lifecycle [OK] nenhum servidor HTTP ativo em {host}:{port}.")
    else:
        if not port_free:
            logger.critical(
                f"Lifecycle: porta {host}:{port} já está em uso — abortar. "
                "Outra instância pode estar rodando."
            )
            sys.exit(1)
        logger.info(f"Lifecycle [OK] porta {host}:{port} livre.")

    # Probe 2: Ollama
    try:
        result = rag.ollama.check_connection()
        if not result.get("connected", False):
            logger.critical("Lifecycle: Ollama não está acessível — abortar.")
            sys.exit(1)
        logger.info("Lifecycle [OK] Ollama acessível.")
    except Exception as e:
        logger.critical(f"Lifecycle: falha ao verificar Ollama: {e} — abortar.")
        sys.exit(1)

    # Probe 3: PostgreSQL
    try:
        rag.db.get_inventory_stats()
        logger.info("Lifecycle [OK] PostgreSQL acessível.")
    except Exception as e:
        logger.critical(f"Lifecycle: PostgreSQL inacessível: {e} — abortar.")
        sys.exit(1)

    bus.emit("server.started", {"transport": transport, "host": host, "port": port})
    logger.info("Lifecycle: todas as probes passaram.")


# ─── ModelGuard drain ─────────────────────────────────────────────────────────

def drain_model_guard(timeout_s: float = DRAIN_TIMEOUT_SECONDS) -> None:
    """Aguarda o ModelGuard liberar o lock antes do shutdown (máx timeout_s)."""
    try:
        from src.services.model_guard import get_model_guard
        guard = get_model_guard()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if guard.stats().get("holder") is None:
                logger.debug("Lifecycle: ModelGuard liberado, shutdown seguro.")
                return
            time.sleep(0.1)
        logger.warning(
            f"Lifecycle: ModelGuard ainda segurado após {timeout_s:.0f}s de dreno — "
            "continuando shutdown."
        )
    except Exception as e:
        logger.warning(f"Lifecycle: drain_model_guard ignorado: {e}")


# ─── Signal handlers ──────────────────────────────────────────────────────────

def setup_signal_handlers(exit_fn) -> None:
    """Registra SIGINT e SIGTERM (se disponível) para chamar exit_fn e encerrar o processo.

    Usa os._exit(0) em vez de sys.exit(0) para garantir que todas as threads
    daemon (heartbeat, uvicorn workers) sejam encerradas imediatamente sem
    aguardar join. O exit_fn deve já ter feito o flush de telemetria antes disso.
    """

    def _handler(signum, frame):
        logger.info(f"Lifecycle: sinal {signum} recebido — iniciando shutdown.")
        exit_fn()
        os._exit(0)

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (OSError, ValueError, AttributeError):
        # SIGTERM pode não estar disponível em alguns contextos Windows
        pass
