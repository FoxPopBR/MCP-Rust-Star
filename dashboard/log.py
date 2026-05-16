"""Logger dedicado do dashboard.

Escreve em logs/dashboard.log com rotação. NUNCA usa logs/mcp_error.log
(arquivo do servidor RAG) — ver memória feedback_dashboard_principles.md:
contenção de file lock entre dashboard e servidor foi a causa raiz do freeze
de 2026-05-15/16.

Sem StreamHandler para stderr: Rich Live controla a tela inteira e bytes
soltos no stderr aparecem como lixo visual. Quem precisar de bell de stderr
emite explicitamente; logs estruturados vão só pro arquivo.
"""
import logging
import os
from logging.handlers import RotatingFileHandler


class _WinCompatRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler tolerante a PermissionError no Windows."""

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except (PermissionError, OSError):
            pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except PermissionError:
            pass
        except Exception:
            self.handleError(record)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_PATH = os.path.join(_PROJECT_ROOT, "logs", "dashboard.log")


def _build_logger() -> logging.Logger:
    lg = logging.getLogger("dashboard")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if lg.handlers:
        return lg

    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    handler = _WinCompatRotatingFileHandler(
        _LOG_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    )
    lg.addHandler(handler)
    return lg


log = _build_logger()
