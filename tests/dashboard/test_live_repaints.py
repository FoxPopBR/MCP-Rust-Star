"""Regression suite — Live de Rich precisa repintar a cada update().

Promovido a partir de `tools/diag_live_freeze.py` (Phase 1 skill diagnose).
Garante que a combinação atual usada pelo dashboard (`auto_refresh=True`,
`refresh_per_second=25`) realmente repinta o terminal entre frames. Se este
arquivo voltar a falhar, é sinal de regressão para o bug do "primeiro frame
congelado" documentado no ADR 0012.

Cobertura:
    test_auto_refresh_true_repaints     → fix #2 (config atual do dashboard)
    test_manual_refresh_repaints        → fix #1 (refresh() explícito)
    test_no_refresh_freezes             → reprodução do bug original

Execução:
    pytest tests/dashboard/test_live_repaints.py
"""
from __future__ import annotations

import io
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel


def _make_panel(n: int) -> Panel:
    return Panel(f"frame={n} ts={time.time():.4f}", title="live-repaint-test")


def _run(auto_refresh: bool, manual_refresh: bool) -> tuple[int, int, int, int]:
    buf = io.StringIO()
    console = Console(
        file=buf,
        force_terminal=True,
        width=80,
        height=24,
        color_system="truecolor",
        legacy_windows=False,
    )
    with Live(
        _make_panel(0),
        console=console,
        screen=True,
        auto_refresh=auto_refresh,
        refresh_per_second=10,
    ) as live:
        b0 = len(buf.getvalue())
        live.update(_make_panel(1))
        if manual_refresh:
            live.refresh()
        time.sleep(0.2)
        b1 = len(buf.getvalue())
        live.update(_make_panel(2))
        if manual_refresh:
            live.refresh()
        time.sleep(0.2)
        b2 = len(buf.getvalue())
        live.update(_make_panel(3))
        if manual_refresh:
            live.refresh()
        time.sleep(0.2)
        b3 = len(buf.getvalue())
    return b0, b1, b2, b3


def test_auto_refresh_true_repaints():
    _, b1, b2, b3 = _run(auto_refresh=True, manual_refresh=False)
    assert b2 > b1, f"Live(auto_refresh=True) não repintou após o segundo update() (b1={b1}, b2={b2})"
    assert b3 > b2, f"Live(auto_refresh=True) não repintou após o terceiro update() (b2={b2}, b3={b3})"


def test_manual_refresh_repaints():
    _, b1, b2, b3 = _run(auto_refresh=False, manual_refresh=True)
    assert b2 > b1, f"live.refresh() manual não repintou após o segundo update() (b1={b1}, b2={b2})"
    assert b3 > b2, f"live.refresh() manual não repintou após o terceiro update() (b2={b2}, b3={b3})"


def test_no_refresh_freezes():
    b0, b1, b2, b3 = _run(auto_refresh=False, manual_refresh=False)
    deltas = (b1 - b0, b2 - b1, b3 - b2)
    assert deltas[1] == 0 and deltas[2] == 0, (
        f"Esperava congelamento sem auto_refresh nem refresh() manual, mas houve repaint: deltas={deltas}"
    )
