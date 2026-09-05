# ── tests/test_djen_job_selecao_oab.py ───────────────────────────────────────
# AUD27-P3-9 teve duas metades. A primeira (já corrigida) fez
# `capturar_para_advogado` resolver a OAB do PERFIL quando `djen_oab_numero`
# está vazio. A segunda é esta: o job das 06h30 selecionava do banco apenas
# `djen_oab_numero IS NOT NULL`, então quem tinha só o campo do perfil nunca
# chegava àquela resolução — o fallback existia e não alcançava o job diário.
#
# O critério de inclusão é o MESMO `oab_para_captura` que a captura usa. Quem
# tem OAB registrada sem UF determinável segue de fora: incluí-lo só produziria
# `oab_nao_configurada` em massa, pintando o heartbeat de vermelho sem que nada
# tivesse mudado — esse caso é reportado por `configurar_oab_djen --verificar`,
# que é onde se conserta cadastro.
from __future__ import annotations

from types import SimpleNamespace

from app.services.djen_service import oab_para_captura
from app.services.scheduler import djen_entra_no_job as _entra_no_job


def _u(djen=None, uf=None, perfil=None):
    return SimpleNamespace(djen_oab_numero=djen, djen_oab_uf=uf, oab_number=perfil)


def test_campo_dedicado_preenchido_entra():
    assert _entra_no_job(_u(djen="252599", uf="MG")) is True


def test_so_o_perfil_com_uf_entra():
    assert _entra_no_job(_u(perfil="252599/MG")) is True
    assert _entra_no_job(_u(perfil="OAB/MG 252599")) is True


def test_perfil_sem_uf_fica_de_fora():
    assert _entra_no_job(_u(perfil="252599")) is False
    assert _entra_no_job(_u(perfil="OAB 252599")) is False


def test_sem_oab_nenhuma_fica_de_fora():
    assert _entra_no_job(_u()) is False
    assert _entra_no_job(_u(perfil="")) is False


def test_meio_par_no_campo_dedicado_continua_entrando():
    """Quem tem `djen_oab_numero` sem UF é uma configuração QUEBRADA, não uma
    ausência: precisa continuar entrando para virar `oab_nao_configurada` no
    diagnóstico, em vez de sumir do relatório."""
    assert _entra_no_job(_u(djen="252599", uf=None)) is True


def test_campo_dedicado_vence_o_perfil():
    u = _u(djen="252599", uf="MG", perfil="111111/SP")
    assert _entra_no_job(u) is True
    assert oab_para_captura(u) == ("252599", "MG")
