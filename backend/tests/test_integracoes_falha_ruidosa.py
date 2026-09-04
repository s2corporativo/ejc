"""Duas fontes públicas que falhavam sem dizer — verificadas ao vivo em 04/09/2026.

1. **Querido Diário**: o cliente apontava para `api.queridodiario.ok.org.br`,
   host que parou de terminar TLS (handshake failure antes de qualquer HTTP).
   A integração inteira respondia erro 100% do tempo. A API migrou para
   `api.queridodiario.org.br`, com o mesmo contrato.

2. **LexML**: o endpoint de busca passou a responder HTTP 200 com HTML de
   desafio anti-bot. `raise_for_status()` passava, o parse de XML estourava, e
   o erro virava `return []`. O ingestor rodava as ~53 consultas do plano,
   recebia vazio em todas e reportava `(0, 0)` como execução BEM-SUCEDIDA —
   federação LexML→RAG entregando zero, sem sinal de falha. É a mesma classe
   do achado V2-3.1: monitorar resultado, não execução.

O que estes testes travam não é a indisponibilidade (não controlamos o Senado
nem o Cloudflare): é a REAÇÃO a ela. Fonte fora do ar tem de falhar alto.
"""
from __future__ import annotations

import pytest

from app.services.jurisprudencia_externa import (
    LexMLBloqueadoError,
    _e_intersticio_antibot,
)


class _RespostaFake:
    def __init__(self, content_type: str, texto: str):
        self.headers = {"content-type": content_type}
        self.text = texto


_HTML_DESAFIO = (
    "<!DOCTYPE html><html><head><title>Verificação de segurança — "
    "Senado Federal</title></head><body><script>proof-of-work</script></body></html>"
)

_XML_OK = (
    '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
    "<entry><title>Acórdão</title></entry></feed>"
)


# ── detecção do interstício ──────────────────────────────────────────────────

def test_html_de_desafio_e_reconhecido():
    assert _e_intersticio_antibot(_RespostaFake("text/html; charset=utf-8", _HTML_DESAFIO))


def test_xml_legitimo_nunca_e_confundido_com_desafio():
    """Falso positivo aqui derrubaria ingestão que está funcionando."""
    assert not _e_intersticio_antibot(
        _RespostaFake("application/xml; charset=utf-8", _XML_OK)
    )
    assert not _e_intersticio_antibot(_RespostaFake("text/xml", _XML_OK))


def test_html_sem_marcador_de_desafio_nao_dispara():
    """Exige content-type HTML E marcador — só um dos dois não basta."""
    assert not _e_intersticio_antibot(
        _RespostaFake("text/html", "resultado da busca sem nada suspeito")
    )


# ── o ingestor não pode mais reportar sucesso com zero ───────────────────────

async def test_plano_todo_bloqueado_falha_alto_em_vez_de_retornar_zero(monkeypatch):
    """Regressão do defeito principal: (0, 0) silencioso virava 'sucesso'."""
    from app.services.ingestors import lexml as ingestor

    async def _sempre_bloqueado(*a, **k):
        raise LexMLBloqueadoError("desafio anti-bot")

    monkeypatch.setattr(ingestor, "buscar_lexml", _sempre_bloqueado)

    with pytest.raises(LexMLBloqueadoError) as exc:
        await ingestor.ingerir(db=None)

    assert "anti-bot" in str(exc.value).lower()


async def test_bloqueio_parcial_nao_derruba_a_execucao(monkeypatch):
    """Se parte das consultas passa, a ingestão segue — só o total bloqueado
    caracteriza 'a federação não rodou'."""
    from app.services.ingestors import lexml as ingestor

    chamadas = {"n": 0}

    async def _bloqueia_a_primeira(*a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise LexMLBloqueadoError("desafio anti-bot")
        return []          # demais consultas respondem, sem itens

    monkeypatch.setattr(ingestor, "buscar_lexml", _bloqueia_a_primeira)

    novos, total = await ingestor.ingerir(db=None)
    assert (novos, total) == (0, 0)
    assert chamadas["n"] > 1, "as consultas seguintes têm de ser tentadas"


# ── host do Querido Diário ───────────────────────────────────────────────────

def test_querido_diario_aponta_para_o_host_vivo():
    """O host antigo (`.ok.org.br`) não termina mais TLS."""
    from app.integrations.querido_diario_client import QUERIDO_DIARIO_BASE

    assert QUERIDO_DIARIO_BASE == "https://api.queridodiario.org.br"
    assert ".ok.org.br" not in QUERIDO_DIARIO_BASE


def test_timeout_cobre_a_latencia_medida_do_host_novo():
    """`/cities` foi medido em 23,1 s — com o timeout antigo (20 s) a chamada
    virava 'indisponível' sem a fonte estar fora do ar."""
    from app.integrations.querido_diario_client import QueridoDiarioClient

    assert QueridoDiarioClient().timeout.read >= 30.0
