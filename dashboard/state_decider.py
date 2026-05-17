"""Decisor puro do estado visual do dashboard.

Lê o snapshot atômico publicado pelo servidor em `data/dashboard_state.json`
e devolve a tupla (status, label, color) que alimenta o LED do header e o
footer. Sem I/O, sem efeitos colaterais — testável isoladamente.

Convenções de campo (sincronizadas com TelemetryWriter v2):
- `snapshot["server"]["activity"]` ∈ {"idle", "active", "error"}
- `snapshot["server"]["alive"]` — flag de heartbeat; ausente ⇒ offline
- `snapshot["ts"]` — ISO 8601 wallclock do servidor (frescor por subtração)

`spinner` foi removido do retorno — quem decide se mostra spinner é a UI,
baseada em `fetcher.ready` (estado transitório de fetching), não no estado
do servidor. Spinner não deve permanecer girando quando o servidor está
ativo mas estabilizado; isso confunde "trabalhando" com "carregando".
"""

import datetime
from typing import TypedDict, Literal

STATUS_OFFLINE = "offline"
STATUS_ERROR = "error"
STATUS_ACTIVE = "active"
STATUS_STANDBY = "standby"

# > 2× HEARTBEAT_SECONDS (10s) — tolera atraso de uma batida sem flicker.
STALE_THRESHOLD_SECONDS = 25.0


class DashboardState(TypedDict):
    status: Literal["active", "standby", "error", "offline"]
    label: str
    color: str


def _is_stale(ts_str: str | None) -> bool:
    if not ts_str:
        return True
    try:
        ts = datetime.datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return True
    diff = (datetime.datetime.now() - ts).total_seconds()
    return diff > STALE_THRESHOLD_SECONDS


def decide_state(snapshot: dict | None) -> DashboardState:
    """Função pura: snapshot → estado visual.

    Ordem de prioridade: offline > error > active > standby.
    Offline tem prioridade absoluta porque sem heartbeat fresco, qualquer
    outro campo é informação obsoleta — não importa o que o JSON dizia.
    """
    if not snapshot:
        return {
            "status": STATUS_OFFLINE,
            "label": "Servidor Offline",
            "color": "#6b7280",
        }

    if _is_stale(snapshot.get("ts")):
        return {
            "status": STATUS_OFFLINE,
            "label": "Servidor Offline",
            "color": "#6b7280",
        }

    server = snapshot.get("server") or {}
    if not server.get("alive", False):
        return {
            "status": STATUS_OFFLINE,
            "label": "Servidor Offline",
            "color": "#6b7280",
        }

    activity = server.get("activity", "idle")

    if activity == "error":
        return {
            "status": STATUS_ERROR,
            "label": "Erro no Servidor",
            "color": "#ef4444",
        }

    if activity == "active":
        return {
            "status": STATUS_ACTIVE,
            "label": "Servidor Ativo",
            "color": "#22c55e",
        }

    return {
        "status": STATUS_STANDBY,
        "label": "Servidor em Standby",
        "color": "#eab308",
    }
