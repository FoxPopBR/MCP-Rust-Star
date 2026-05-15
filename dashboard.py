import os
import json
import time
import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn, TaskProgressColumn
from rich.text import Text
from rich.columns import Columns

# Calcula caminhos absolutos baseados na localização deste script
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ROOT_DIR, "logs", "mcp_error.log")
STATE_FILE = os.path.join(ROOT_DIR, "data", "current_indexing.json")
BATCH_FILE = os.path.join(ROOT_DIR, "data", "batch_progress.json")

console = Console()

def get_last_logs(n=20):
    """Lê as últimas N linhas do log e aplica cores."""
    if not os.path.exists(LOG_PATH):
        return [Text("Log não encontrado.", style="dim red")]
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            styled_lines = []
            for line in lines[-n:]:
                line = line.strip()
                if not line: continue
                
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
                else:
                    text.append(" ℹ ", style="cyan")
                    text.append(line, style="white")
                styled_lines.append(text)
            return styled_lines
    except:
        return [Text("Erro ao ler log (acesso bloqueado).", style="dim red")]

def get_state():
    """Lê o estado em tempo real gerado pelo RAGService."""
    if not os.path.exists(STATE_FILE):
        return {
            "stats": {"new": 0, "cached": 0, "skipped": 0, "errors": 0},
            "current_file": "Aguardando...",
            "current_folder": "-",
            "project_id": "-"
        }
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def make_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="side", ratio=1),
        Layout(name="body", ratio=2)
    )
    return layout

class DashboardApp:
    def __init__(self):
        self.layout = make_layout()
        
    def generate_side_panel(self, state):
        stats = state.get("stats", {})
        
        # Tabela de Métricas
        table = Table.grid(expand=True)
        table.add_column(style="cyan", width=15)
        table.add_column(style="bold white")
        
        table.add_row("🚀 Projeto:", state.get("project_id", "-"))
        table.add_row("📂 Pasta:", state.get("current_folder", "-")[:30])
        table.add_row("📄 Arquivo:", state.get("current_file", "IDLE")[:30])
        table.add_section()
        table.add_row("✅ Novos:", f"[green]{stats.get('new', 0)}[/]")
        table.add_row("💎 Cache:", f"[blue]{stats.get('cached', 0)}[/]")
        table.add_row("⏩ Ignorados:", f"[dim white]{stats.get('skipped', 0)}[/]")
        table.add_row("❌ Erros:", f"[bold red]{stats.get('errors', 0)}[/]")
        
        return Panel(
            table, 
            title="[bold]ESTADO ATUAL[/]", 
            border_style="cyan",
            padding=(1, 2)
        )

    def generate_header(self):
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        now = datetime.datetime.now().strftime("%H:%M:%S")
        grid.add_row(
            Text(" 🛸 ANTIGRAVITY ENGINE", style="bold magenta"),
            Text("RAG KNOWLEDGE SERVER DASHBOARD", style="bold white"),
            Text(f"🕒 {now} ", style="bold cyan")
        )
        return Panel(grid, style="blue")

    def update(self):
        state = get_state()
        if not state: return self.layout

        # Header
        self.layout["header"].update(self.generate_header())
        
        # Side Panel (Stats)
        self.layout["side"].update(self.generate_side_panel(state))
        
        # Body Panel (Logs)
        logs = get_last_logs(25)
        log_text = Text("\n").join(logs)
        self.layout["body"].update(
            Panel(log_text, title="[bold]TERMINAL DE EVENTOS[/]", border_style="yellow")
        )
        
        # Footer
        footer_text = Text(" Status: ", style="white", justify="center")
        if state.get("current_file"):
            footer_text.append("RUNNING", style="bold blink green")
        else:
            footer_text.append("IDLE", style="bold yellow")
            
        self.layout["footer"].update(Panel(footer_text, style="dim"))
        
        return self.layout

if __name__ == "__main__":
    app = DashboardApp()
    with Live(app.update(), refresh_per_second=4, screen=True) as live:
        try:
            while True:
                live.update(app.update())
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
