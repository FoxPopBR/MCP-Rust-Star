import atexit
import os
import subprocess
import sys
import threading
import time
import datetime

try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.box import DOUBLE_EDGE, ROUNDED

from .fetcher import DataFetcher
from .log import log
from .state_decider import decide_state

# ── Caminhos e configuração ────────────────────────────────────────────────────

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(_PROJECT_ROOT, "data", "dashboard_state.json")
_PID_FILE = os.path.join(_PROJECT_ROOT, "data", "dashboard.pid")

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:8b")
RAG_MODEL = os.getenv("RAG_MODEL", "qwen3.5:9b")
CONTEXT_WINDOW = os.getenv("CONTEXT_WINDOW", "12288")

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


# ── Single-instance (PID file) ─────────────────────────────────────────────────

def _kill_pid(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        log.warning("não foi possível encerrar PID %d: %s", pid, e)


_PS_FIND_DASHBOARDS = (
    "Get-CimInstance Win32_Process "
    "-Filter \"Name='python.exe' or Name='pythonw.exe'\" "
    "| Where-Object { $_.CommandLine -match 'dashboard' } "
    "| ForEach-Object { $_.ProcessId }"
)


def _find_dashboard_pids() -> list[int]:
    """Lista PIDs de processos Python rodando qualquer variante do dashboard.

    Usa PowerShell Get-CimInstance porque `wmic` foi removido a partir do
    Windows 11 24H2 (sem ele, o single-instance falhava silenciosamente e
    duas instâncias coexistiam). Casa o command line contra qualquer
    referência a 'dashboard' — pega tanto `python -m dashboard` quanto
    invocações com caminho absoluto via .venv.
    """
    pids: list[int] = []
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", _PS_FIND_DASHBOARDS],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        log.error("PowerShell enumerate error: %s", e)
        return pids

    current_pid = os.getpid()
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid != current_pid:
            pids.append(pid)
    return pids


def _enforce_single_instance() -> None:
    """Encerra qualquer instância anterior do dashboard antes de iniciar.

    Varre todos os processos Python — não confia apenas no PID file, que pode
    estar ausente, corrompido, ou referir-se a uma das múltiplas instâncias
    órfãs (o caso que travou o dashboard antes desta refatoração).
    """
    killed: list[int] = []
    for pid in _find_dashboard_pids():
        log.info("encerrando instância anterior (PID %d)", pid)
        _kill_pid(pid)
        killed.append(pid)
    if killed:
        time.sleep(0.5)

    try:
        with open(_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        atexit.register(_cleanup_pid_file)
    except Exception as e:
        log.error("PID file write error: %s", e)


def _cleanup_pid_file() -> None:
    try:
        if os.path.exists(_PID_FILE):
            os.remove(_PID_FILE)
    except Exception:
        pass


# ── Helpers ────────────────────────────────────────────────────────────────────

def spinner_frame(active: bool = True) -> str:
    if not active:
        return "·"
    return _SPINNER[int(time.time() * 8) % len(_SPINNER)]


def fmt_bytes(b: int) -> str:
    if b >= 1024 ** 3:
        return f"{b / 1024**3:.1f} GB"
    if b >= 1024 ** 2:
        return f"{b / 1024**2:.0f} MB"
    return f"{b} B"


def trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _colorize_log_lines(lines: list[str]) -> list[Text]:
    """Aplica estilos Rich às linhas brutas do log produzidas pelo fetcher.

    Função pura — sem I/O. As linhas vêm do tail incremental do background.
    """
    styled: list[Text] = []
    for line in lines:
        text = Text()
        if "ERROR" in line or "FALHA" in line:
            text.append(" ✖ ", style="bold red")
            text.append(line, style="red")
        elif "WARNING" in line:
            text.append(" ⚠ ", style="yellow")
            text.append(line, style="yellow")
        elif "DEBUG" in line:
            text.append(" ⚙ ", style="dim blue")
            text.append(line, style="dim blue")
        elif "INFO" in line:
            text.append(" ℹ ", style="cyan")
            text.append(line, style="white")
        else:
            text.append(" · ", style="dim")
            text.append(line, style="dim white")
        styled.append(text)
    return styled


# ── Layout ─────────────────────────────────────────────────────────────────────

def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3),
    )
    layout["main"].split_row(
        Layout(name="side", ratio=1),
        Layout(name="body", ratio=2),
    )
    layout["side"].split_column(
        Layout(name="side_top", ratio=2),
        Layout(name="side_bottom", ratio=1),
    )
    return layout


# ── DashboardApp ───────────────────────────────────────────────────────────────

class DashboardApp:
    def __init__(self, fetcher: DataFetcher) -> None:
        self.fetcher = fetcher
        self.layout = make_layout()
        self._start_time = time.time()
        self._was_busy = False
        self._completed_at: float | None = None
        self._completed_project = ""
        self._completed_elapsed = ""
        self._prev_batch_active: bool = False
        self._ring_bell = False
        # Scroll state para o inventário (controlado por setas do teclado)
        self._inv_lock = threading.Lock()
        self._inv_page = 0
        self._inv_total_pages = 1
        # Rastreia quando a última atividade terminou
        self._idle_since: float | None = None

    def _elapsed(self) -> str:
        secs = int(time.time() - self._start_time)
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}h{m:02d}m{s:02d}s" if h else f"{m:02d}m{s:02d}s"

    def _fmt_idle(self) -> str:
        """Retorna tempo ocioso formatado."""
        if self._idle_since is None:
            return ""
        secs = int(time.time() - self._idle_since)
        if secs < 60:
            return f"{secs}s"
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"

    def _throughput(self, new_count: int) -> str:
        elapsed = time.time() - self._start_time
        if elapsed < 1 or new_count == 0:
            return "—"
        return f"{new_count / (elapsed / 60):.1f} arq/min"

    # ── Detecção de conclusão (sem efeitos colaterais de render) ───────────────

    def _detect_completion(self, state: dict | None, batch: dict | None) -> None:
        """Atualiza _was_busy e agenda bell. Chamado em update(), fora do render."""
        is_busy = bool(state and state.get("current_file"))
        batch_running = bool(batch and batch.get("running"))

        if batch_running:
            self._completed_at = None

        if self._was_busy and not is_busy and state and not batch_running:
            self._completed_at = time.time()
            self._completed_project = state.get("project_id", "")
            started_at_str = state.get("started_at")
            if started_at_str:
                try:
                    started = datetime.datetime.fromisoformat(started_at_str)
                    secs = int((datetime.datetime.now() - started).total_seconds())
                    h, rem = divmod(secs, 3600)
                    m, s = divmod(rem, 60)
                    self._completed_elapsed = (
                        f"{h}h{m:02d}m{s:02d}s" if h else f"{m:02d}m{s:02d}s"
                    )
                except Exception as e:
                    log.warning("elapsed calc: %s", e)
                    self._completed_elapsed = self._elapsed()
            else:
                self._completed_elapsed = self._elapsed()
            self._ring_bell = True

        self._was_busy = is_busy

    # ── Painéis — funções puras (sem I/O, sem side effects) ───────────────────

    def generate_header(self, data: dict) -> Panel:
        online = data["online"]          # Ollama — HTTP ping a cada 2s
        ps = data["ps"]
        mcp_alive = data.get("mcp_alive", False)  # MCP Server — HTTP ping a cada 2s
        raw_snap = data.get("raw_snapshot")

        # DB status: só confiável se o servidor MCP estiver vivo e reportando
        db_ok = False
        if mcp_alive and raw_snap:
            db_ok = raw_snap.get("server", {}).get("db_ok", False)

        # Status do servidor: baseado no ping HTTP real, não no arquivo
        if mcp_alive:
            # Servidor respondeu ao ping — verificar atividade via snapshot
            v_state = decide_state(raw_snap)
        else:
            v_state = {
                "status": "offline",
                "label": "Servidor Offline",
                "color": "#6b7280",
            }

        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1.2)
        grid.add_column(justify="center", ratio=1.6)
        grid.add_column(justify="right", ratio=1.2)

        right_cell = Text(justify="right")

        # LED de Status do Servidor MCP (baseado em ping HTTP real)
        led = "●"
        right_cell.append(f"{led} ", style=f"bold {v_state['color']}")
        right_cell.append(f"{v_state['label'].upper()} ", style=f"bold {v_state['color']}")

        # Status do Ollama (ping HTTP real a cada 2s)
        if online:
            right_cell.append(" | OLLAMA ✓", style="dim green")
        else:
            right_cell.append(" | OLLAMA ✗", style="bold red")

        # Status do DB (derivado do servidor quando vivo)
        if not mcp_alive:
            right_cell.append(" | DB ?", style="dim yellow")
        elif db_ok:
            right_cell.append(" | DB ✓", style="dim green")
        else:
            right_cell.append(" | DB ✗", style="bold red")

        if ps:
            total_vram = sum(m.get("size_vram", 0) for m in ps.get("models", []))
            if total_vram > 0:
                right_cell.append(f"  |  VRAM: {fmt_bytes(total_vram)}", style="bold cyan")

        now = datetime.datetime.now().strftime("%H:%M:%S")
        right_cell.append(f"  🕒 {now} ", style="bold cyan")

        grid.add_row(
            Text(" 🛸  ANTIGRAVITY ELITE", style="bold magenta"),
            Text("🛰️  MCP KNOWLEDGE ENGINE SYSTEM v2.0", style="bold white"),
            right_cell,
        )
        return Panel(grid, style="blue", box=DOUBLE_EDGE)

    def generate_monitor_panel(self, data: dict, s_active: bool = True) -> Panel:
        state = data["state"]
        ps = data["ps"]

        table = Table.grid(expand=True)
        table.add_column(style="dim cyan", width=8)
        table.add_column()

        for label, model in [("Embed.:", EMBEDDING_MODEL), ("RAG M.:", RAG_MODEL)]:
            is_loaded = False
            model_info = None
            if ps:
                for m in ps.get("models", []):
                    if m.get("name") == model:
                        is_loaded = True
                        model_info = m
                        break
                        
            t = Text()
            if is_loaded:
                t.append("● ", style="bold green")
                t.append(model, style="bold green")
                # Cálculos do Ollama PS (Tamanho e Proc CPU/GPU)
                size_gb = model_info.get("size", 0) / (1024**3)
                total_size = model_info.get("size", 0)
                if total_size > 0:
                    gpu_pct = int((model_info.get("size_vram", 0) / total_size) * 100)
                    cpu_pct = 100 - gpu_pct
                else:
                    gpu_pct = 0
                    cpu_pct = 100
                t.append(f"\n   ↳ {size_gb:.1f}GB | {cpu_pct}%/{gpu_pct}% CPU/GPU", style="dim green")
            elif ps is not None:
                t.append("○ ", style="dim white")
                t.append(model, style="dim white")
            else:
                t.append(f"{spinner_frame(s_active)} ", style="dim yellow")
                t.append(model, style="dim yellow")
                
            table.add_row(label, t)

        active_contexts = []
        if ps:
            for m in ps.get("models", []):
                name = m.get("name", "")
                ctx = m.get("context_length", 0)
                if ctx > 0:
                    short_name = name.split(":")[0]
                    active_contexts.append(f"{ctx} ({short_name})")
        
        if active_contexts:
            ctx_str = " | ".join(active_contexts)
            table.add_row("Conte.:", Text(f"{ctx_str}", style="dim green"))
        else:
            table.add_row("Conte.:", Text("-", style="dim"))
        table.add_row("Uptime:", Text(self._elapsed(), style="dim"))

        if state is None:
            table.add_section()
            table.add_row(
                "", Text(f"{spinner_frame(s_active)} Carregando estado...", style="dim yellow")
            )
            return Panel(
                table,
                title="[bold blue]🛰️  TELEMETRY SYSTEM[/]",
                border_style="cyan",
                padding=(1, 1),
                box=ROUNDED,
            )

        stats = state.get("stats", {})
        new_count = stats.get("new", 0)
        cached = stats.get("cached", 0)
        skipped = stats.get("skipped", 0)
        errors = stats.get("errors", 0)
        total_all = new_count + cached
        last_query = state.get("last_query", {})

        table.add_section()

        project_id = state.get("project_id", "")
        if project_id:
            self._idle_since = None  # Reset idle timer
            table.add_row("Projeto:", Text(project_id, style="bold cyan"))
            folder = state.get("current_folder", "")
            if folder:
                table.add_row("Pasta:", Text(trunc(folder, 22), style="dim white"))
            cur_file = state.get("current_file", "")
            if cur_file:
                ext = os.path.splitext(cur_file)[1].lower()
                is_vision = ext in (".png", ".jpg", ".jpeg", ".webp")
                file_style = "bold magenta" if is_vision else "white"
                table.add_row("Arquivo:", Text(trunc(cur_file, 22), style=file_style))
                if is_vision:
                    table.add_row("Modo:", Text("VISION 👁️", style="bold magenta"))

            cur_frag = state.get("current_fragment", 0)
            tot_frag = state.get("total_fragments", 0)
            if tot_frag > 0:
                ratio = cur_frag / tot_frag
                filled = int(10 * ratio)
                frag_text = Text()
                frag_text.append(
                    f"[{'█' * filled}{'░' * (10 - filled)}]", style="bold blue"
                )
                frag_text.append(
                    f" {cur_frag}/{tot_frag} ({ratio*100:.0f}%)", style="dim"
                )
                table.add_row("Frag.:", frag_text)

            total_expected = state.get("total_expected", 0)
            if total_expected > 0:
                prog_ratio = min(total_all / total_expected, 1.0)
                filled = int(20 * prog_ratio)
                prog_text = Text()
                prog_text.append(
                    f"[{'█' * filled}{'░' * (20 - filled)}]", style="bold green"
                )
                prog_text.append(
                    f" {total_all}/{total_expected} ({prog_ratio*100:.0f}%)", style="dim"
                )
                table.add_row("Prog.:", prog_text)
        else:
            # Rastreia tempo ocioso
            if self._idle_since is None:
                self._idle_since = time.time()
            idle_str = self._fmt_idle()
            standby_t = Text()
            standby_t.append("[ STANDBY ]", style="dim yellow")
            if idle_str:
                standby_t.append(f"  idle {idle_str}", style="dim")
            table.add_row("Projeto:", standby_t)
            table.add_row("Pasta:", Text("-", style="dim"))
            table.add_row("Arquivo:", Text("-", style="dim"))
            table.add_row("Frag.:", Text("-", style="dim"))
            table.add_row("Prog.:", Text("-", style="dim"))

            table.add_section()

        table.add_row("Novos:", Text(str(new_count), style="bold green"))

        cache_str = str(cached)
        if total_all > 0:
            cache_str += f"  ({cached/total_all*100:.1f}% reaprov.)"
        table.add_row("Cache:", Text(cache_str, style="bold yellow"))
        table.add_row("Pulad.:", Text(str(skipped), style="dim"))
        err_text = Text()
        err_text.append(str(errors), style="bold red" if errors > 0 else "dim green")
        if errors > 0 and total_all > 0:
            err_pct = errors / (total_all + errors) * 100
            err_text.append(f"  ({err_pct:.1f}%)", style="dim red")
        table.add_row("Erros:", err_text)

        vel_text = Text()
        vel_text.append(self._throughput(new_count), style="bold cyan")
        # ETA estimado quando indexando
        if project_id and new_count > 0:
            total_expected = state.get("total_expected", 0)
            if total_expected > 0:
                elapsed_s = time.time() - self._start_time
                if elapsed_s > 5:  # Espera 5s para estabilizar
                    rate = new_count / elapsed_s
                    remaining = total_expected - total_all
                    if remaining > 0 and rate > 0:
                        eta_s = int(remaining / rate)
                        eta_m, eta_ss = divmod(eta_s, 60)
                        eta_h, eta_m = divmod(eta_m, 60)
                        eta_str = f"{eta_h}h{eta_m:02d}m" if eta_h else f"{eta_m}m{eta_ss:02d}s"
                        vel_text.append(f"  ETA ~{eta_str}", style="dim yellow")
        table.add_row("Vel.:", vel_text)

        # Listagem de arquivos com falha
        error_files = state.get("error_files", [])
        if error_files:
            table.add_section()
            table.add_row("FALHAS:", Text(f"{len(error_files)} arquivo(s)", style="bold red"))
            for item in error_files[-3:]:  # Exibe os últimos 3 erros
                fname = os.path.basename(item.get("file", ""))
                err_msg = item.get("error", "desconhecido")
                table.add_row(
                    f" • {trunc(fname, 10)}:",
                    Text(trunc(err_msg, 20), style="dim red"),
                )

        if last_query.get("question"):
            table.add_section()
            q_status = last_query.get("status", "IDLE")
            q_time = last_query.get("time", "-")
            s_style = (
                "bold green"
                if q_status == "SUCCESS"
                else "bold red" if q_status == "ERROR" else "dim"
            )
            table.add_row(
                "Query:",
                Text(trunc(last_query.get("question", "-"), 22), style="italic dim"),
            )
            table.add_row("Status:", Text(f"{q_status} @ {q_time}", style=s_style))

        return Panel(
            table,
            title="[bold blue]🛰️  TELEMETRY SYSTEM[/]",
            border_style="cyan",
            padding=(1, 1),
            box=ROUNDED,
        )

    def generate_batch_panel(self, batch: dict | None) -> Panel:
        if not batch:
            batch = {}
        bq = batch.get("queue", [])
        bcurrent = batch.get("current_project")
        bcompleted = batch.get("completed", [])
        btotal = batch.get("total_projects", 0)
        bdone = len(bcompleted)

        text = Text()
        
        if not bcurrent and not bq and not bcompleted:
            text.append("  [ STANDBY ]\n", style="dim yellow")
            text.append("  Nenhum projeto na fila\n", style="dim")
        else:
            text.append(f" {bdone}/{btotal} concluídos\n\n", style="bold cyan")

            for pid in reversed(bcompleted[-3:]):
                text.append("  ✓ ", style="bold green")
                text.append(f"{pid}\n", style="green")

            if bcurrent:
                text.append("  ▶ ", style="bold yellow")
                text.append(f"{bcurrent}\n", style="bold yellow")

            for pid in bq:
                text.append("  ○ ", style="dim white")
                text.append(f"{pid}\n", style="white")

        return Panel(
            text,
            title="[bold cyan]⟳ FILA DE PROJETOS[/]",
            border_style="cyan",
            padding=(0, 1),
            box=ROUNDED,
        )

    def generate_inventory_panel(self, state: dict | None, s_active: bool = True) -> Panel:
        if state is None:
            return Panel(
                Text(
                    f"{spinner_frame(s_active)} Carregando inventário...",
                    justify="center",
                    style="dim yellow",
                ),
                title="[bold yellow]⊕ DATABASE INVENTORY[/]",
                border_style="yellow",
                box=ROUNDED,
            )

        inventory = state.get("inventory", {})
        if not inventory:
            return Panel(
                Text("⏳ Sincronizando...", justify="center", style="dim"),
                title="[bold yellow]⊕ DATABASE INVENTORY[/]",
                border_style="yellow",
                box=ROUNDED,
            )

        total_files = sum(v.get("total", 0) for v in inventory.values())
        total_frags = sum(v.get("fragments", 0) for v in inventory.values())
        text = Text()

        # Paginação controlada por setas do teclado (▲/▼)
        inv_items = list(inventory.items())
        per_page = 4
        self._inv_total_pages = max(1, (len(inv_items) + per_page - 1) // per_page)
        
        # Clampa a página ao range válido
        if self._inv_page >= self._inv_total_pages:
            self._inv_page = self._inv_total_pages - 1
        if self._inv_page < 0:
            self._inv_page = 0
            
        start_idx = self._inv_page * per_page
        end_idx = start_idx + per_page
        page_items = inv_items[start_idx:end_idx]

        for pid, info in page_items:
            files = info.get("total", 0)
            frags = info.get("fragments", 0)
            pct = frags / total_frags * 100 if total_frags > 0 else 0
            if frags == 0:
                color = "yellow"
            elif pct >= 50:
                color = "green"
            else:
                color = "cyan"
            
            text.append(f"  {pid.upper()}", style=f"bold {color}")
            text.append(f"  {frags:,} frags", style=f"bold {color}")
            text.append(f" | {files:,} files", style=color)
            text.append(f"  ({pct:.0f}%)\n", style=f"dim {color}")

            exts = info.get("extensions", {})
            top_exts = sorted(exts.items(), key=lambda x: -x[1])[:6]
            if top_exts:
                text.append(
                    f"  {'  '.join(f'{e}:{n}' for e, n in top_exts)}\n\n", style="dim"
                )
            else:
                text.append("  (Vazio)\n\n", style="dim")

        # Indicador de navegação
        if self._inv_total_pages > 1:
            nav = Text()
            up_style = "bold cyan" if self._inv_page > 0 else "dim"
            down_style = "bold cyan" if self._inv_page < self._inv_total_pages - 1 else "dim"
            nav.append("  ▲ ", style=up_style)
            nav.append(f" Pág {self._inv_page + 1}/{self._inv_total_pages} ", style="dim yellow")
            nav.append(" ▼", style=down_style)
            nav.append("  (↑↓ setas)", style="dim")
            text.append(nav)
            text.append("\n", style="dim")

        text.append(f"  TOTAL GLOBAL: {total_frags:,} fragmentos", style="bold white")
        text.append(f"  |  {total_files:,} arquivos em {len(inventory)} projeto(s)", style="dim white")

        return Panel(
            text,
            title="[bold yellow]⊕ DATABASE INVENTORY[/]",
            border_style="yellow",
            box=ROUNDED,
        )

    def generate_footer(self, state: dict | None, batch: dict | None, v_state: dict, s_active: bool = False) -> Panel:
        is_busy = bool(state and state.get("current_file"))

        if self._completed_at and (time.time() - self._completed_at) < 30:
            text = Text(justify="center")
            text.append(" ✓ INDEXAÇÃO CONCLUÍDA", style="bold green")
            text.append(f"  ─  {self._completed_project}", style="dim green")
            text.append(f"  ─  em {self._completed_elapsed}", style="dim green")
            return Panel(text, style="dim")

        text = Text(" Status: ", style="white", justify="center")
        if is_busy:
            text.append("SYSTEM BUSY", style="bold green")
            text.append(
                f"  ─  {state.get('project_id', '')}  ›  {state.get('current_file', '')}",
                style="dim green",
            )
        elif not self.fetcher.ready:
            text.append(f"{spinner_frame(s_active)} Inicializando...", style="dim yellow")
        else:
            text.append(v_state["label"].upper(), style=f"bold {v_state['color']}")
            text.append(f"  ─  {v_state['status'].upper()}", style=f"dim {v_state['color']}")

        return Panel(text, style="dim")

    # ── Layout hot-swap ────────────────────────────────────────────────────────

    def _apply_layout(self) -> None:
        if getattr(self, "_layout_applied", False):
            return
        # Sempre exibir a fila de processamento (Batch)
        self.layout["side"].split_column(
            Layout(name="side_top", ratio=3),
            Layout(name="side_batch", ratio=2),
            Layout(name="side_bottom", ratio=2),
        )
        self._layout_applied = True

    # ── Ciclo de renderização (apenas UI — sem I/O, sem side effects) ──────────

    def update(self) -> Layout:
        data = self.fetcher.get()
        state = data["state"]
        batch = data["batch"]
        raw_snap = data.get("raw_snapshot")
        mcp_alive = data.get("mcp_alive", False)
        
        # Status do servidor: baseado em ping HTTP real
        if mcp_alive:
            v_state = decide_state(raw_snap)
        else:
            v_state = {
                "status": "offline",
                "label": "Servidor Offline",
                "color": "#6b7280",
            }
        # Spinner = transient fetching, NÃO server activity. Gira só enquanto
        # esperamos um snapshot aparecer; uma vez estabilizado, o LED+texto
        # do header já comunica o estado sem animação ruidosa.
        s_active = self.fetcher.is_fetching or not self.fetcher.ready

        # Detecção de conclusão fora das funções de render (sem efeitos colaterais).
        self._detect_completion(state, batch)

        # Bell via stderr — seguro enquanto Rich Live controla stdout/tela.
        if self._ring_bell:
            sys.stderr.write("\a")
            sys.stderr.flush()
            self._ring_bell = False

        self._apply_layout()

        self.layout["header"].update(self.generate_header(data))
        self.layout["footer"].update(self.generate_footer(state, batch, v_state, s_active))
        self.layout["side_top"].update(self.generate_monitor_panel(data, s_active))
        self.layout["side_batch"].update(self.generate_batch_panel(batch))
        self.layout["side_bottom"].update(self.generate_inventory_panel(state, s_active))

        # Linhas brutas vêm do tail incremental do fetcher; aqui só colorimos.
        raw = self.fetcher.get_log_lines()
        logs = _colorize_log_lines(raw)
        log_text = (
            Text("\n").join(logs)
            if logs
            else Text(f"{spinner_frame(s_active)} Aguardando logs...", style="dim yellow")
        )
        self.layout["body"].update(
            Panel(
                log_text,
                title="[bold yellow]⚡ EVENT TERMINAL[/]",
                border_style="yellow",
            )
        )

        return self.layout


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    _enforce_single_instance()
    os.system("cls" if os.name == "nt" else "clear")

    fetcher = DataFetcher(OLLAMA_URL, STATE_FILE)
    app = DashboardApp(fetcher)

    # Aguarda o fetcher completar o primeiro ciclo de leitura de arquivos (máx 500ms).
    # Garante que o primeiro frame já exibe dados reais, não o estado "Carregando...".
    deadline = time.time() + 0.5
    while not fetcher.ready and time.time() < deadline:
        time.sleep(0.02)

    try:
        initial = app.update()
    except Exception:
        log.exception("render error (initial frame)")
        raise

    stop_event = threading.Event()

    # ── Keyboard listener (setas ↑↓ para scroll do inventário) ──────────
    def _keyboard_listener():
        if not _HAS_MSVCRT:
            return
        while not stop_event.is_set():
            try:
                if msvcrt.kbhit():
                    ch = msvcrt.getch()
                    # Setas no Windows: primeiro byte 0xe0 ou 0x00, segundo byte é o código
                    if ch in (b'\xe0', b'\x00'):
                        arrow = msvcrt.getch()
                        with app._inv_lock:
                            if arrow == b'H':  # ↑ Up
                                app._inv_page = max(0, app._inv_page - 1)
                            elif arrow == b'P':  # ↓ Down
                                app._inv_page = min(app._inv_total_pages - 1, app._inv_page + 1)
                    elif ch == b'\x03':  # Ctrl+C
                        stop_event.set()
                        break
                else:
                    time.sleep(0.05)
            except Exception:
                time.sleep(0.1)

    kb_thread = threading.Thread(target=_keyboard_listener, daemon=True)
    kb_thread.start()

    with Live(
        initial,
        screen=True,
        auto_refresh=True,
        refresh_per_second=25,
    ) as live:
        try:
            while not stop_event.is_set():
                try:
                    live.update(app.update())
                except Exception:
                    log.exception("render error")
                stop_event.wait(0.25)
        except KeyboardInterrupt:
            stop_event.set()
        finally:
            fetcher.stop()


if __name__ == "__main__":
    main()
