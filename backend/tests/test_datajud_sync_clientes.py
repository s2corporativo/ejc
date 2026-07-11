"""Sync DataJud com notificação ao cliente (datajud_sync_service):
detecção de andamento NOVO (dedup pela mesma chave [dj:hash] do
datajud_service) + template determinístico do e-mail de andamento.
Testes puros — sem banco nem rede."""
from __future__ import annotations

from app.services.datajud_service import _hash_mov
from app.services.datajud_sync_service import (
    ASSINATURA_AUTOMATICA,
    MAX_ANDAMENTOS_EMAIL,
    filtrar_movimentos_novos,
    hora_sync_clientes_utc,
    limpar_descricao,
    montar_email_andamentos,
)


def _mov(data: str, descricao: str) -> dict:
    return {"data": data, "codigo": None, "descricao": descricao}


# ── Detecção de andamento novo ─────────────────────────────────────────────────

def test_filtrar_novos_ignora_ja_importados_pela_chave_dj():
    ja = _mov("2026-07-01T10:00:00", "Juntada de petição")
    h = _hash_mov("2026-07-01", "Juntada de petição")
    existentes = [f"Juntada de petição [dj:{h}]"]

    novos = filtrar_movimentos_novos(
        [ja, _mov("2026-07-08T09:00:00", "Sentença publicada")], existentes
    )
    assert [n["descricao"] for n in novos] == ["Sentença publicada"]


def test_filtrar_novos_sem_existentes_retorna_todos():
    movs = [_mov("2026-07-01", "A"), _mov("2026-07-02", "B")]
    assert filtrar_movimentos_novos(movs, []) == movs


def test_filtrar_novos_deduplica_dentro_do_proprio_lote():
    movs = [_mov("2026-07-01T08:00:00", "Despacho"),
            _mov("2026-07-01T08:00:00", "Despacho")]
    assert len(filtrar_movimentos_novos(movs, [])) == 1


def test_filtrar_novos_descricao_sem_marcador_dj_nao_conta_como_existente():
    # Movimento manual na timeline (sem [dj:hash]) não bloqueia a importação.
    novos = filtrar_movimentos_novos(
        [_mov("2026-07-01", "Despacho")], ["Despacho (nota manual do advogado)"]
    )
    assert len(novos) == 1


def test_limpar_descricao_remove_sufixo_tecnico():
    h = _hash_mov("2026-07-01", "Sentença")
    assert limpar_descricao(f"Sentença [dj:{h}]") == "Sentença"
    assert limpar_descricao("Sentença") == "Sentença"


# ── Template do e-mail de andamento ────────────────────────────────────────────

def test_email_andamentos_assunto_e_conteudo():
    numero = "0000001-02.2020.8.13.0000"
    assunto, corpo = montar_email_andamentos(
        numero, [_mov("2026-07-08T09:00:00", "Sentença publicada")]
    )
    assert assunto == (
        f"[De Paula Teixeira Advogados] Movimentação no processo {numero}"
    )
    assert numero in corpo
    assert "08/07/2026" in corpo
    assert "Sentença publicada" in corpo
    assert ASSINATURA_AUTOMATICA in corpo
    # Canal proibido e metadado interno jamais aparecem.
    assert "whatsapp" not in corpo.lower()
    assert "[dj:" not in corpo


def test_email_andamentos_limita_lista_e_informa_excedente():
    movs = [_mov(f"2026-07-{d:02d}", f"Movimento {d}") for d in range(1, 9)]
    _, corpo = montar_email_andamentos("123", movs)
    listados = sum(1 for d in range(1, 9) if f"Movimento {d}" in corpo)
    assert listados == MAX_ANDAMENTOS_EMAIL
    assert f"e mais {len(movs) - MAX_ANDAMENTOS_EMAIL} andamento(s)" in corpo


def test_email_andamentos_sem_excedente_nao_menciona_e_mais():
    _, corpo = montar_email_andamentos("123", [_mov("2026-07-01", "Único")])
    assert "e mais" not in corpo


# ── Horário do job (parse defensivo, padrão backup_service) ────────────────────

def test_hora_sync_default_e_valores_invalidos(monkeypatch):
    from app.services import datajud_sync_service as svc
    monkeypatch.setattr(svc.settings, "DATAJUD_SYNC_HORA_UTC", "07:15")
    assert hora_sync_clientes_utc() == (7, 15)
    monkeypatch.setattr(svc.settings, "DATAJUD_SYNC_HORA_UTC", "25:99")
    assert hora_sync_clientes_utc() == (9, 30)  # fallback seguro
    monkeypatch.setattr(svc.settings, "DATAJUD_SYNC_HORA_UTC", "banana")
    assert hora_sync_clientes_utc() == (9, 30)
