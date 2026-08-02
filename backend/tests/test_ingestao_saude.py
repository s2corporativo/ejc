"""Bloco 5 — monitorar RESULTADO, não execução.

O defeito que estes testes travam: a captura do DJEN reportou "sucesso" durante
meses sem nunca ter registrado uma intimação, e três painéis distintos
confirmaram que estava tudo bem. Nenhum deles perguntava se o job tinha
ENTREGADO alguma coisa — só se ele tinha RODADO.

Cada teste abaixo corresponde a um estado real encontrado pela auditoria em
produção, e não a um caso hipotético.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.ingestao_saude import (
    LIMITE_EXECUCOES_ZERADAS,
    avaliar_fontes,
    avaliar_saude_fonte,
    resumir,
)

AGORA = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _fonte(**kw):
    """Fonte saudável por padrão; cada teste altera só o que importa."""
    base = dict(
        slug="fonte_x",
        ativo=True,
        ultima_execucao=AGORA - timedelta(hours=2),
        ultimo_status="sucesso",
        ultimo_erro=None,
        registros_novos=10,
        registros_total=100,
        execucoes_zeradas_consecutivas=0,
        agora=AGORA,
    )
    base.update(kw)
    return avaliar_saude_fonte(**base)


# ── O caso DJEN: rodou, reportou sucesso, nunca entregou nada ────────────────


def test_fonte_que_nunca_produziu_e_critica_mesmo_reportando_sucesso():
    """O estado exato do `djen`: ultimo_status 'sucesso', registros_total 0."""
    s = _fonte(ultimo_status="sucesso", registros_novos=0, registros_total=0)
    assert s.situacao == "nunca_produziu"
    assert s.critico is True
    assert "zero" in s.motivo.lower()


def test_nunca_produziu_vence_dormente():
    """Os três `juris_import_*`: ativos, dormentes há 7 dias e com zero histórico.

    Reportar 'dormente' aqui subestimaria o problema — a fonte não parou de
    funcionar, ela nunca funcionou.
    """
    s = _fonte(
        ultima_execucao=AGORA - timedelta(days=7),
        registros_novos=0,
        registros_total=0,
    )
    assert s.situacao == "nunca_produziu"


# ── O caso anpd: erro sem mensagem ───────────────────────────────────────────


def test_erro_sem_mensagem_e_reportado_como_sem_diagnostico():
    """`anpd` falhava com `ultimo_erro: null` — impossível investigar pelo painel."""
    s = _fonte(ultimo_status="erro", ultimo_erro=None)
    assert s.situacao == "erro_sem_diagnostico"
    assert s.critico is True
    assert "captura da exceção" in s.acao


def test_erro_com_mensagem_e_erro_comum():
    s = _fonte(ultimo_status="erro", ultimo_erro="HTTPError: 503")
    assert s.situacao == "erro"
    assert s.critico is True
    assert "503" in s.motivo


def test_erro_com_mensagem_so_de_espacos_conta_como_sem_diagnostico():
    s = _fonte(ultimo_status="erro", ultimo_erro="   ")
    assert s.situacao == "erro_sem_diagnostico"


# ── Fonte que tinha histórico e parou ────────────────────────────────────────


def test_fonte_produtiva_que_zera_n_vezes_seguidas_e_critica():
    s = _fonte(
        registros_novos=0,
        registros_total=500,
        execucoes_zeradas_consecutivas=LIMITE_EXECUCOES_ZERADAS,
    )
    assert s.situacao == "parou_de_produzir"
    assert s.critico is True


def test_uma_execucao_vazia_isolada_nao_alarma():
    """Período genuinamente sem julgados novos não pode virar alarme falso."""
    s = _fonte(registros_novos=0, registros_total=500, execucoes_zeradas_consecutivas=1)
    assert s.situacao == "ok"
    assert s.critico is False


# ── Execução parcial: não é ok, não é run vazio ──────────────────────────────


def test_execucao_parcial_nao_sai_como_ok():
    """Parcial persiste em vários ingestores (knowledge, juris, DataJud).

    Parte do lote falhou — reportar 'ok' esconderia exatamente o tipo de perda
    silenciosa que este módulo existe para denunciar.
    """
    s = _fonte(ultimo_status="parcial", ultimo_erro="HTTPError: 503 no lote 2")
    assert s.situacao == "parcial"
    assert s.critico is False
    assert "503" in s.motivo
    assert s.acao != "Nenhuma."


def test_parcial_tem_severidade_propria_acima_de_ok():
    s = _fonte(ultimo_status="parcial")
    assert s.to_dict()["severidade"] > 0


def test_parcial_nao_mascara_fonte_que_nunca_produziu():
    """Fonte parcial com acervo eternamente zerado é 'nunca_produziu', pior."""
    s = _fonte(
        ultimo_status="parcial",
        registros_novos=0,
        registros_total=0,
        ja_produziu=False,
    )
    assert s.situacao == "nunca_produziu"


# ── Consulta legítima com zero resultados não apaga o histórico ──────────────


def test_fonte_que_ja_produziu_nao_vira_nunca_produziu_apos_consulta_zerada():
    """`registros_total` é sobrescrito a cada execução.

    Uma consulta legítima com zero resultados zeraria o 'histórico' e faria uma
    fonte produtiva parecer que nunca funcionou — o marcador vitalício
    `ja_produziu` é a memória que não se perde.
    """
    s = _fonte(registros_novos=0, registros_total=0, ja_produziu=True)
    assert s.situacao != "nunca_produziu"
    assert s.situacao == "ok"
    assert s.critico is False


def test_sem_marcador_vitalicio_cai_no_comportamento_legado():
    """Linha de banco ainda sem a migration 125: deriva do estado da última
    execução, como antes."""
    s = _fonte(registros_novos=0, registros_total=0, ja_produziu=None)
    assert s.situacao == "nunca_produziu"


# ── Dormência e desativação ──────────────────────────────────────────────────


def test_fonte_ativa_parada_ha_muito_tempo_e_dormente_mas_nao_critica():
    s = _fonte(ultima_execucao=AGORA - timedelta(days=30))
    assert s.situacao == "dormente"
    assert s.critico is False


def test_fonte_desativada_nao_gera_alarme():
    """Fonte desligada de propósito não é falha — e não pode poluir o painel."""
    s = _fonte(ativo=False, registros_total=0, registros_novos=0)
    assert s.situacao == "ok"
    assert s.critico is False


def test_fonte_saudavel_e_ok():
    assert _fonte().situacao == "ok"


# ── Resumo para o painel ─────────────────────────────────────────────────────


class _Row:
    def __init__(self, slug, **kw):
        self.slug = slug
        self.ativo = kw.get("ativo", True)
        self.ultima_execucao = kw.get("ultima_execucao", AGORA - timedelta(hours=1))
        self.ultimo_status = kw.get("ultimo_status", "sucesso")
        self.ultimo_erro = kw.get("ultimo_erro")
        self.registros_novos = kw.get("registros_novos", 5)
        self.registros_total = kw.get("registros_total", 50)
        self.execucoes_zeradas_consecutivas = kw.get("execucoes_zeradas_consecutivas", 0)


def test_resumo_nomeia_as_fontes_criticas_em_vez_de_so_contar():
    """Um número não diz por onde começar.

    Foi a ausência dessa lista que deixou o DJEN passar despercebido no meio de
    fontes verdes.
    """
    fontes = [
        _Row("stj"),
        _Row("djen", registros_novos=0, registros_total=0),
        _Row("anpd", ultimo_status="erro", ultimo_erro=None),
    ]
    resumo = resumir(avaliar_fontes(fontes, agora=AGORA))

    assert resumo["status_geral"] == "critico"
    assert resumo["criticas"] == ["anpd", "djen"]
    assert resumo["total_criticas"] == 2
    assert resumo["total"] == 3


def test_resumo_de_fontes_saudaveis_e_ok():
    resumo = resumir(avaliar_fontes([_Row("stj"), _Row("planalto")], agora=AGORA))
    assert resumo["status_geral"] == "ok"
    assert resumo["criticas"] == []


def test_avaliar_fontes_tolera_linha_sem_a_coluna_nova():
    """Linha vinda de banco ainda sem a migration 125 não pode derrubar o painel."""

    class _Legada:
        slug = "legada"
        ativo = True
        ultima_execucao = AGORA - timedelta(hours=1)
        ultimo_status = "sucesso"
        ultimo_erro = None
        registros_novos = 3
        registros_total = 30

    saudes = avaliar_fontes([_Legada()], agora=AGORA)
    assert saudes["legada"].situacao == "ok"


# ── Contador de execuções improdutivas ───────────────────────────────────────


class _FonteFake:
    def __init__(self, zeradas=0, ja_produziu=False):
        self.slug = "fonte_x"
        self.ultima_execucao = None
        self.ultimo_status = None
        self.registros_novos = 0
        self.registros_total = 0
        self.ultimo_erro = None
        self.execucoes_zeradas_consecutivas = zeradas
        self.ja_produziu = ja_produziu


class _DBFake:
    def __init__(self, fonte):
        self._fonte = fonte

    async def execute(self, *_a, **_kw):
        fonte = self._fonte

        class _R:
            def scalar_one_or_none(self):
                return fonte

        return _R()


async def _marcar(fonte, **kw):
    from app.services.ingestion_service import marcar_execucao

    await marcar_execucao(_DBFake(fonte), "fonte_x", **kw)
    return fonte


async def test_execucao_vazia_incrementa_o_contador():
    f = await _marcar(_FonteFake(zeradas=2), status="sucesso", novos=0, total=0)
    assert f.execucoes_zeradas_consecutivas == 3


async def test_execucao_produtiva_zera_o_contador():
    f = await _marcar(_FonteFake(zeradas=9), status="sucesso", novos=4, total=10)
    assert f.execucoes_zeradas_consecutivas == 0


async def test_execucao_com_erro_nao_mexe_no_contador():
    """O problema de uma execução com erro já é o erro — não confundir os sinais."""
    f = await _marcar(_FonteFake(zeradas=2), status="erro", novos=0, total=0, erro="boom")
    assert f.execucoes_zeradas_consecutivas == 2


async def test_execucao_parcial_nao_reseta_nem_incrementa_o_contador():
    """Parcial não é sucesso pleno: não pode apagar o histórico de zeradas.

    Antes deste ajuste, um run parcial com novos>0 resetava o contador como se
    tudo estivesse bem — e a fonte quebrada ganhava sobrevida no painel.
    """
    f = await _marcar(
        _FonteFake(zeradas=2), status="parcial", novos=4, total=10, erro="boom"
    )
    assert f.execucoes_zeradas_consecutivas == 2

    f = await _marcar(_FonteFake(zeradas=2), status="parcial", novos=0, total=0)
    assert f.execucoes_zeradas_consecutivas == 2


async def test_ingestao_idempotente_saudavel_nao_incrementa():
    """Job semanal do Planalto reprocessa o catálogo fixo: novos=0, total>0.

    Registros RECEBIDOS porém inalterados não são coletor quebrado — três runs
    assim não podem transformar a fonte em `parou_de_produzir`.
    """
    f = await _marcar(_FonteFake(zeradas=2), status="sucesso", novos=0, total=120)
    assert f.execucoes_zeradas_consecutivas == 0


async def test_execucao_produtiva_marca_ja_produziu_para_sempre():
    """O marcador vitalício que blinda a fonte contra `nunca_produziu`."""
    f = await _marcar(_FonteFake(), status="sucesso", novos=4, total=10)
    assert f.ja_produziu is True

    # Consulta legítima zerada em seguida NÃO apaga o marcador.
    await _marcar(f, status="sucesso", novos=0, total=0)
    assert f.ja_produziu is True


async def test_execucao_zerada_nao_marca_ja_produziu():
    f = await _marcar(_FonteFake(), status="sucesso", novos=0, total=0)
    assert f.ja_produziu is False


async def test_erro_sem_mensagem_grava_texto_diagnosticavel():
    """Nunca mais um `ultimo_erro: null` no painel."""
    f = await _marcar(_FonteFake(), status="erro", novos=0, total=0, erro=None)
    # marcar_execucao preserva None; quem preenche é executar_ingestao. Aqui só
    # garantimos que o contrato de marcar_execucao não inventa texto.
    assert f.ultimo_erro is None

    from pathlib import Path

    fonte_service = (
        Path(__file__).parents[1] / "app" / "services" / "ingestion_service.py"
    ).read_text(encoding="utf-8")
    assert 'if status == "erro" and not (erro or "").strip():' in fonte_service, (
        "executar_ingestao precisa garantir mensagem quando a exceção não traz texto"
    )


def test_tjmg_conta_itens_brutos_antes_do_parsing():
    """Distinguir 'nada veio' de 'veio e não parseou' — item 4 do bloco."""
    from pathlib import Path

    fonte = (
        Path(__file__).parents[1] / "app" / "services" / "ingestors" / "tjmg.py"
    ).read_text(encoding="utf-8")
    assert "brutos += len(itens or [])" in fonte
    assert "itens brutos recebidos" in fonte
