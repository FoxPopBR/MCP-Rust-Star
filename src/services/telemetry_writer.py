"""Writer único de telemetria para o dashboard.

Centraliza a escrita do arquivo `data/dashboard_state.json` consumido pelo
dashboard. Substitui o pipeline antigo (current_indexing.json + embed_batch.json
+ tail físico do mcp_error.log) por um único snapshot atômico publicado pelo
próprio servidor.

Princípios:
- Throttle de 250ms entre escritas físicas (atualizações em memória são livres).
- Escrita atômica via .tmp + os.replace (não corrompe se interromper).
- Inventory (Postgres) consultado com cache TTL — não consulta a cada frame.
- Falha de telemetria NUNCA derruba o servidor: try/except largo no persist.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import threading
import time
from collections import Counter
from typing import Any

from tools.logger import logger

SCHEMA_VERSION = 2
DASHBOARD_STATE_FILE = os.path.join("data", "dashboard_state.json")
WRITE_THROTTLE_SECONDS = 0.25
INVENTORY_TTL_SECONDS = 60.0
LOG_TAIL_LINES = 28
HEARTBEAT_SECONDS = 10.0
ACTIVITY_LABELS = ("idle", "active", "error")


class InventoryProvider:
    """Consulta o inventário do Postgres com cache TTL.

    Retorna `{project_id: {"total": int, "extensions": {ext: count}}}`.
    Usa `db.list_sources()` (já existente) e agrega em memória, evitando SQL
    custom. Custo aceitável porque o resultado fica cacheado por 60s.
    """

    def __init__(self, db) -> None:
        self._db = db
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}
        self._cache_ts: float = 0.0

    def fetch(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            if self._cache and (now - self._cache_ts) < INVENTORY_TTL_SECONDS:
                return self._cache

        try:
            # Novo método que retorna estatísticas agregadas (file_count + frag_count)
            stats_list = self._db.get_inventory_stats()
        except Exception as e:
            logger.warning(f"InventoryProvider: get_inventory_stats falhou: {e}")
            return self._cache or {}

        result = {}
        for item in stats_list:
            pid = item["project_id"]
            result[pid] = {
                "total": item["file_count"],    # Mantemos 'total' como arquivos para compatibilidade
                "fragments": item["frag_count"], # Nova chave para fragmentos reais
                "extensions": item["extensions"]
            }

        with self._lock:
            self._cache = result
            self._cache_ts = now
        return result

    def invalidate(self) -> None:
        """Força nova consulta no próximo fetch (chamar após indexação)."""
        with self._lock:
            self._cache_ts = 0.0


class TelemetryWriter:
    """Publica snapshots de telemetria em `dashboard_state.json`.

    O servidor chama `write(embed_state, rag_state)` em pontos de mutação.
    O writer faz throttle (250ms) e escrita atômica internamente.
    """

    def __init__(
        self,
        state_file: str = DASHBOARD_STATE_FILE,
        inventory: InventoryProvider | None = None,
    ) -> None:
        self._state_file = state_file
        self._inventory = inventory
        self._lock = threading.Lock()
        self._last_write_ts: float = 0.0
        self._pending_payload: dict[str, Any] | None = None
        self._last_payload: dict[str, Any] | None = None

        self._activity_lock = threading.Lock()
        self._activity_count = 0
        self._activity_error = False

        os.makedirs(os.path.dirname(self._state_file) or ".", exist_ok=True)

    def _current_activity_label(self) -> str:
        with self._activity_lock:
            if self._activity_error:
                return "error"
            return "active" if self._activity_count > 0 else "idle"

    def enter_activity(self) -> None:
        """Marca o servidor como ativo (refcount). Pareie com exit_activity()."""
        with self._activity_lock:
            self._activity_count += 1

    def exit_activity(self) -> None:
        """Decrementa o refcount de atividade. Nunca vai abaixo de zero."""
        with self._activity_lock:
            if self._activity_count > 0:
                self._activity_count -= 1

    def set_activity_error(self, error: bool = True) -> None:
        """Marca o servidor em estado de erro (sobrescreve idle/active)."""
        with self._activity_lock:
            self._activity_error = error

    @contextlib.contextmanager
    def activity(self):
        """Context manager: marca atividade durante o escopo e libera no exit."""
        self.enter_activity()
        try:
            yield
        finally:
            self.exit_activity()

    def heartbeat_loop(self, stop_event: threading.Event, get_embed_state_fn, get_rag_state_fn, get_batch_progress_fn, get_server_extra_fn) -> None:
        """Loop de heartbeat que toca o arquivo a cada HEARTBEAT_SECONDS."""
        logger.debug(f"TelemetryWriter: Heartbeat iniciado (intervalo={HEARTBEAT_SECONDS}s)")
        while not stop_event.is_set():
            try:
                self.write(
                    embed_state=get_embed_state_fn(),
                    rag_state=get_rag_state_fn(),
                    batch_progress=get_batch_progress_fn(),
                    server_extra=get_server_extra_fn(),
                )
            except Exception as e:
                logger.warning(f"TelemetryWriter: Falha no heartbeat: {e}")
            
            # Dorme em pequenos pedaços para responder rápido ao stop_event
            for _ in range(int(HEARTBEAT_SECONDS * 2)):
                if stop_event.is_set():
                    break
                time.sleep(0.5)
        logger.debug("TelemetryWriter: Heartbeat finalizado.")

    def snapshot(
        self,
        embed_state: dict[str, Any],
        rag_state: dict[str, Any] | None = None,
        batch_progress: dict[str, Any] | None = None,
        server_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rag_state = rag_state or {}
        batch_progress = batch_progress or {}
        server_extra = server_extra or {}

        inventory = {}
        if self._inventory is not None:
            try:
                inventory = self._inventory.fetch()
            except Exception as e:
                logger.warning(f"TelemetryWriter: inventory fetch falhou: {e}")

        log_lines = embed_state.get("log_lines", []) or []
        log_tail = list(log_lines[-LOG_TAIL_LINES:])

        return {
            "version": SCHEMA_VERSION,
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "ts_monotonic": time.monotonic(),
            "activity": self._current_activity_label(),
            "server": {
                "alive": True,
                "last_query": server_extra.get("last_query"),
            },
            "indexing": {
                "running": embed_state.get("running", False),
                "canceled": embed_state.get("canceled", False),
                "current_project": embed_state.get("current_project"),
                "current_file": embed_state.get("current_file"),
                "current_folder": rag_state.get("current_folder", ""),
                "current_fragment": embed_state.get("current_fragment"),
                "total_fragments": embed_state.get("total_fragments"),
                "total_expected": embed_state.get("total_expected", 0),
                "stats": dict(embed_state.get("stats", {}) or rag_state.get("stats", {})),
                "stats_by_ext": dict(embed_state.get("stats_by_ext", {})),
                "error_files": list(embed_state.get("error_files", [])),
                "queue": list(embed_state.get("queue", [])),
                "completed": list(embed_state.get("completed", [])),
                "started_at": embed_state.get("started_at"),
                "finished_at": embed_state.get("finished_at"),
                "total_projects": embed_state.get("total_projects", 0),
            },
            "batch": {
                "completed": list(batch_progress.get("completed", [])),
                "results": dict(batch_progress.get("results", {})),
            },
            "inventory": inventory,
            "log_tail": log_tail,
        }

    def persist(self, payload: dict[str, Any]) -> None:
        """Escreve payload no disco respeitando throttle e atomicidade.

        Se outra escrita ocorreu há menos de 250ms, guarda o payload mais
        recente e descarta — o próximo write() flush aproveitará o slot.
        """
        now = time.monotonic()
        with self._lock:
            if (now - self._last_write_ts) < WRITE_THROTTLE_SECONDS:
                self._pending_payload = payload
                return
            self._last_write_ts = now
            self._pending_payload = None

        self._atomic_write(payload)

    def flush(self, payload: dict[str, Any] | None = None) -> None:
        """Força escrita imediata ignorando throttle (usar em shutdown)."""
        with self._lock:
            target = payload or self._pending_payload
            self._last_write_ts = time.monotonic()
            self._pending_payload = None
        if target is not None:
            self._atomic_write(target)

    def write(
        self,
        embed_state: dict[str, Any],
        rag_state: dict[str, Any] | None = None,
        batch_progress: dict[str, Any] | None = None,
        server_extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            payload = self.snapshot(embed_state, rag_state, batch_progress, server_extra)
            self.persist(payload)
        except Exception as e:
            logger.warning(f"TelemetryWriter.write falhou: {e}")

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        tmp_path = f"{self._state_file}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._state_file)
        except Exception as e:
            logger.warning(f"TelemetryWriter._atomic_write falhou: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
