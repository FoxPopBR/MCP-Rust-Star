import datetime
import time
from typing import TypedDict, Literal

class DashboardState(TypedDict):
    status: Literal["active", "standby", "error", "offline"]
    label: str
    color: str  # Hex or CSS color
    spinner: bool

def decide_state(snapshot: dict) -> DashboardState:
    """
    Função pura que decide o estado visual do dashboard baseado no snapshot da telemetria.
    """
    if not snapshot:
        return {
            "status": "offline",
            "label": "Servidor Offline",
            "color": "#6b7280", # Gray
            "spinner": False
        }

    # 1. Verifica frescor do Heartbeat
    # O heartbeat do servidor é a cada 10s. Se tiver mais de 30s, consideramos offline.
    ts_str = snapshot.get("ts")
    is_stale = True
    if ts_str:
        try:
            ts = datetime.datetime.fromisoformat(ts_str)
            now = datetime.datetime.now()
            diff = (now - ts).total_seconds()
            if diff < 30:
                is_stale = False
        except Exception:
            pass

    if is_stale:
        return {
            "status": "offline",
            "label": "Servidor Offline (Stale)",
            "color": "#6b7280", # Gray
            "spinner": False
        }

    # 2. Verifica Erro
    activity = snapshot.get("activity", "idle")
    if activity == "error":
        return {
            "status": "error",
            "label": "Erro no Servidor",
            "color": "#ef4444", # Red
            "spinner": False
        }

    # 3. Verifica Atividade
    if activity == "active":
        return {
            "status": "active",
            "label": "Servidor Ativo",
            "color": "#22c55e", # Green
            "spinner": True
        }

    # 4. Caso contrário: Standby
    return {
        "status": "standby",
        "label": "Servidor em Standby",
        "color": "#eab308", # Yellow
        "spinner": False
    }
