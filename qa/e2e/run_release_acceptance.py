#!/usr/bin/env python3
"""Gate E2E ampliado da release consolidada do EJC.

Reutiliza o runner fictício existente e acrescenta os contratos estruturais
implementados nas ondas de consolidação. Mantém a mesma proteção contra produção,
o mesmo marcador E2E-FICTICIO e o mesmo relatório auditável.
"""
from __future__ import annotations

import run_fictitious_smoke as base


_original_case_followups = base._case_followups


def _case_followups_extended(client, state, matrix) -> None:
    _original_case_followups(client, state, matrix)
    if not state.case_id:
        return

    base._request(
        client,
        state,
        name="processos.canonicos.listar",
        method="GET",
        path=f"/api/cases/{state.case_id}/processes?arquivo=todos",
        expected=[200],
    )
    base._request(
        client,
        state,
        name="casos.timeline_unica",
        method="GET",
        path=f"/api/cases/{state.case_id}/timeline?page=1&per_page=20",
        expected=[200],
    )
    base._request(
        client,
        state,
        name="casos.saude_operacional",
        method="GET",
        path=f"/api/cases/{state.case_id}/operational-health",
        expected=[200],
    )
    base._request(
        client,
        state,
        name="dashboard.saude_carteira",
        method="GET",
        path="/api/dashboard/operational-health?limit=20",
        expected=[200, 403],
    )
    base._request(
        client,
        state,
        name="data_room_v4.adaptador",
        method="GET",
        path="/api/data-room-v4/",
        expected=[200, 403],
    )
    base._request(
        client,
        state,
        name="teses_v4.adaptador",
        method="GET",
        path="/api/teses-v4/",
        expected=[200, 403],
    )


base._case_followups = _case_followups_extended


if __name__ == "__main__":
    base.main()
