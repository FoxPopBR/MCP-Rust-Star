import os
import json
import urllib.request
import threading

from .log import log

_HTTP_TTL = 2.0
_FILE_POLL = 0.25
_LOG_TAIL_LINES = 28


class DataFetcher:
    """Busca dados externos em threads daemon. A UI só lê do cache.

    Dois loops independentes:
      - _file_loop: lê data/dashboard_state.json a cada 0.25s
      - _http_loop: heartbeat Ollama + /api/ps a cada 2.0s

    O snapshot unificado já traz `indexing`, `batch`, `inventory`, `server`
    e `log_tail` — não há mais tail físico de log nem leitura paralela de
    arquivos batch separados.
    """

    def __init__(self, ollama_url: str, state_file: str) -> None:
        self._ollama_url = ollama_url
        self._state_file = state_file

        self._lock = threading.Lock()
        self._data: dict = {"online": False, "ps": None, "state": None, "batch": None}
        self._log_lines: list[str] = []
        self._ready = False
        self._is_fetching = True

        self._stop = threading.Event()

        self._t_files = threading.Thread(target=self._file_loop, daemon=True)
        self._t_http = threading.Thread(target=self._http_loop, daemon=True)
        self._t_files.start()
        self._t_http.start()

    # ── Loops ──────────────────────────────────────────────────────────────────

    def _file_loop(self) -> None:
        """Loop orientado a eventos: reage a mudanças no disco via watchfiles."""
        from watchfiles import watch
        import time

        # Leitura inicial
        try:
            self._refresh_files()
        except Exception:
            pass

        state_dir = os.path.dirname(os.path.abspath(self._state_file))
        state_base = os.path.basename(self._state_file)

        log.info("Fetcher: Modo Event-Driven (watchfiles) iniciado em %s", state_dir)
        
        while not self._stop.is_set():
            try:
                # watch() bloqueia até haver mudança ou stop_event disparar.
                # O timeout de 5s garante que não ficamos travados eternamente
                # se o SO não disparar o evento por algum motivo.
                for changes in watch(state_dir, stop_event=self._stop):
                    for _, path in changes:
                        if os.path.basename(path) == state_base:
                            self._refresh_files()
                            break
            except Exception as e:
                log.warning("watchfiles: %s. Fazendo fallback para polling (2s).", e)
                self._stop.wait(2.0)
                self._refresh_files()

    def _http_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._refresh_http()
            except Exception as e:
                log.warning("http loop: %s", e)
            self._stop.wait(_HTTP_TTL)

    # ── Snapshot polling ───────────────────────────────────────────────────────

    def _read_snapshot(self) -> dict | None:
        if not os.path.exists(self._state_file):
            return None
        try:
            # Atomic read (sort of): if it's being written, we might get partial JSON.
            # No Windows, o lock de escrita do TelemetryWriter (v2) deve evitar isso,
            # mas o try/except lida com JSON malformado temporário.
            with open(self._state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # log.warning("read dashboard_state: %s", e)
            return None

    def _refresh_files(self) -> None:
        snap = self._read_snapshot()
        if snap is None:
            with self._lock:
                # Se o arquivo sumiu/inválido, sinalizamos fetching transitório:
                # a UI mostra spinner enquanto esperamos próxima escrita do server.
                self._data["raw_snapshot"] = None
                self._ready = True
                self._is_fetching = True
            return

        indexing = snap.get("indexing", {}) or {}
        server = snap.get("server", {}) or {}
        inventory = snap.get("inventory", {}) or {}
        log_tail = snap.get("log_tail", []) or []

        # Painéis monitor / inventário / footer leem campos achatados de `state`.
        # Os aliases (project_id ← current_project) preservam o visual existente
        # sem precisar editar cada painel.
        state_view = {
            "project_id": indexing.get("current_project") or "",
            "current_file": indexing.get("current_file") or "",
            "current_folder": indexing.get("current_folder") or "",
            "current_fragment": indexing.get("current_fragment") or 0,
            "total_fragments": indexing.get("total_fragments") or 0,
            "total_expected": indexing.get("total_expected") or 0,
            "stats": indexing.get("stats", {}) or {},
            "started_at": indexing.get("started_at"),
            "finished_at": indexing.get("finished_at"),
            "running": indexing.get("running", False),
            "inventory": inventory,
            "last_query": server.get("last_query") or {},
        }

        # Painel batch lê queue/completed/current/total e o estado running.
        # No schema unificado essas chaves vivem dentro de `indexing` — aqui
        # apenas re-empacotamos para preservar a assinatura do painel.
        batch_view = {
            "running": indexing.get("running", False),
            "queue": indexing.get("queue", []) or [],
            "current_project": indexing.get("current_project") or "",
            "completed": indexing.get("completed", []) or [],
            "total_projects": indexing.get("total_projects", 0) or 0,
        }

        with self._lock:
            self._data["state"] = state_view
            self._data["batch"] = batch_view
            self._data["raw_snapshot"] = snap # Mantemos para o StateDecider
            self._log_lines = list(log_tail[-_LOG_TAIL_LINES:])
            self._ready = True
            self._is_fetching = False

    # ── HTTP polling ───────────────────────────────────────────────────────────

    def _refresh_http(self) -> None:
        online = False
        try:
            with urllib.request.urlopen(
                urllib.request.Request(f"{self._ollama_url}/"), timeout=2
            ) as resp:
                online = resp.status == 200
        except Exception as e:
            log.warning("Ollama heartbeat: %s", e)

        ps_data: dict | None = None
        if online:
            try:
                req = urllib.request.Request(
                    f"{self._ollama_url}/api/ps",
                    headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    ps_data = json.loads(resp.read().decode())
            except Exception as e:
                log.warning("Ollama /api/ps: %s", e)

        with self._lock:
            self._data["online"] = online
            self._data["ps"] = ps_data

    # ── API pública ────────────────────────────────────────────────────────────

    def get(self) -> dict:
        with self._lock:
            return dict(self._data)

    def get_log_lines(self) -> list[str]:
        with self._lock:
            return list(self._log_lines)

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._ready

    @property
    def is_fetching(self) -> bool:
        """True quando o dashboard está aguardando dados aparecerem.

        Spinner deve girar enquanto isto for True (transient loading state).
        Não significa "servidor trabalhando" — para isso use state_decider.
        """
        with self._lock:
            return self._is_fetching

    def stop(self) -> None:
        self._stop.set()
