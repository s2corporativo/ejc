"""Alarme de envelhecimento dos dados jurídicos embutidos (P2-13, #1150).

Súmula-teto e reconferência do seed são constantes Python conferidas à mão numa
data. Envelhecidas em silêncio, produzem erro jurídico com cara de acerto: o
gate antialucinação passa a acusar de inexistente uma súmula NOVA e verdadeira.
Estes testes fixam o alarme — e injetam `hoje` para não depender do relógio.
"""
from datetime import date, timedelta

from app.services import vigencia_dados_juridicos as vdj


def _conferido_em() -> date:
    """A mais ANTIGA das datas de conferência — governa o alarme."""
    datas = [
        vdj._para_data(item["conferido_em"])
        for item in vdj._itens()
    ]
    assert all(datas), "toda constante embutida precisa de data de conferência"
    return min(datas)


def test_itens_cobrem_as_constantes_com_efeito_juridico():
    chaves = {item["chave"] for item in vdj._itens()}
    assert {"sumula_teto", "sumulas_seed"} <= chaves
    for item in vdj._itens():
        # O alarme só serve se disser ONDE reconferir.
        assert item["arquivo"].endswith(".py")
        assert item["descricao"].strip()


def test_dentro_do_prazo_nao_alarma():
    hoje = _conferido_em() + timedelta(days=vdj.LIMITE_DIAS - 1)
    estado = vdj.estado(hoje=hoje)
    assert estado["desatualizado"] is False
    assert estado["alertas"] == []


def test_vencido_alarma_e_diz_onde_reconferir():
    hoje = _conferido_em() + timedelta(days=vdj.LIMITE_DIAS + 1)
    estado = vdj.estado(hoje=hoje)
    assert estado["desatualizado"] is True
    assert estado["alertas"]
    assert any(".py" in a for a in estado["alertas"])


def test_data_ilegivel_e_tratada_como_vencida(monkeypatch):
    """Não saber a idade do dado é o estado que este alarme existe para matar."""
    monkeypatch.setattr(vdj, "_itens", lambda: [
        {"chave": "x", "descricao": "d", "conferido_em": "sem data",
         "arquivo": "backend/app/x.py"},
    ])
    estado = vdj.estado(hoje=date(2026, 8, 18))
    assert estado["desatualizado"] is True
    assert estado["itens"][0]["dias_desde_conferencia"] is None


def test_teto_de_sumula_vencido_isola_o_item_do_teto():
    assert vdj.teto_de_sumula_vencido(hoje=_conferido_em()) is False
    vencido = _conferido_em() + timedelta(days=vdj.LIMITE_DIAS + 1)
    assert vdj.teto_de_sumula_vencido(hoje=vencido) is True


# ── efeito no gate antialucinação ────────────────────────────────────────────

async def test_sumula_acima_do_teto_com_tabela_vencida_ressalva_em_vez_de_negar(
    monkeypatch,
):
    """Teto vencido: o aviso manda conferir na fonte, não afirma inexistência."""
    from app.services import verificador_jurisprudencia as vj

    # O verificador importa a função DENTRO do ramo — o patch vai na origem.
    monkeypatch.setattr(
        "app.services.vigencia_dados_juridicos.teto_de_sumula_vencido",
        lambda hoje=None: True,
    )
    rel = await vj.verificar_jurisprudencia(None, "Aplica-se a Súmula 999 do STJ.")
    avisos = " ".join(c.get("aviso") or "" for c in rel["citacoes"])
    assert "não é reconferida desde" in avisos
    assert "provavelmente não existe" not in avisos


async def test_sumula_acima_do_teto_com_tabela_no_prazo_segue_negando(monkeypatch):
    from app.services import verificador_jurisprudencia as vj

    monkeypatch.setattr(
        "app.services.vigencia_dados_juridicos.teto_de_sumula_vencido",
        lambda hoje=None: False,
    )
    rel = await vj.verificar_jurisprudencia(None, "Aplica-se a Súmula 999 do STJ.")
    avisos = " ".join(c.get("aviso") or "" for c in rel["citacoes"])
    assert "provavelmente não existe" in avisos
