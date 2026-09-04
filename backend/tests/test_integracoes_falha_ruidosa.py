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


# ── proveniência do LexML: ementa ≠ inteiro teor ─────────────────────────────

def test_conteudo_lexml_avisa_que_nao_e_inteiro_teor():
    """O aviso vai no CONTEÚDO porque é o conteúdo que chega ao modelo.

    Sem ele, o trecho recuperado é indistinguível de um documento lido por
    inteiro, e a IA pode afirmar o que a decisão decidiu tendo visto só a
    ementa — que é resumo redigido pelo tribunal, não o julgado.
    """
    from app.services.ingestors.lexml import _monta_conteudo

    conteudo = _monta_conteudo(
        {
            "titulo": "RE 1.234.567/MG",
            "tribunal": "STF",
            "relator": "Min. Fulano",
            "ementa": "Trata-se de recurso extraordinário em que se discute...",
        },
        "jurisprudencia",
    )

    assert "NÃO É O INTEIRO TEOR" in conteudo
    assert "inteiro teor na fonte oficial" in conteudo
    # O aviso precede o texto: quem lê o trecho vê a ressalva antes da ementa.
    assert conteudo.index("PROVENIÊNCIA") < conteudo.index("recurso extraordinário")


def test_aviso_de_proveniencia_nao_engole_o_conteudo_real():
    """A ressalva é acréscimo, não substituição — os metadados seguem citáveis."""
    from app.services.ingestors.lexml import _monta_conteudo

    conteudo = _monta_conteudo(
        {"titulo": "Lei 14.133/2021", "ementa": "Lei de Licitações e Contratos."},
        "legislacao",
    )

    assert "Lei 14.133/2021" in conteudo
    assert "Lei de Licitações e Contratos." in conteudo


# ── correções da revisão de segurança (regra 8) ──────────────────────────────

def test_parse_do_indice_nao_retrocede_em_corpo_hostil():
    """Regressão de ReDoS (P1-1 da revisão de segurança).

    A versão anterior usava `<script[^>]*id="params"[^>]*>(.*?)</script>` com
    re.DOTALL — quadrática: 0,78 MB de `<script` sem fechamento custavam 63,5 s
    de CPU, medidos. Como o parse roda no MESMO event loop da API (o scheduler
    sobe no lifespan do FastAPI), isso congelaria o EJC inteiro sob a premissa
    de worker único. `find`/`index` não retrocedem — este teste falha por
    TIMEOUT se alguém reintroduzir a regex.
    """
    import time

    from app.services.diario_oficial_service import (
        DOUIndisponivelError,
        _extrair_json_do_indice,
    )

    hostil = "<script" * 200_000          # ~1,4 MB sem nenhum '>' de fechamento
    inicio = time.monotonic()
    try:
        _extrair_json_do_indice(hostil)
    except DOUIndisponivelError:
        pass                              # sem o marcador, recusa é o correto
    decorrido = time.monotonic() - inicio

    # Limiar folgado de propósito: o alvo é backtracking QUADRÁTICO (63,5 s
    # medidos para 0,78 MB), não desempenho sub-segundo. Um teto apertado
    # tornaria este teste sensível à carga da máquina — assertiva de tempo que
    # falha por ruído é pior que assertiva nenhuma, porque ensina a equipe a
    # ignorar o vermelho. 5 s separa "linear" de "quadrático" com sobra.
    assert decorrido < 5.0, (
        f"parse levou {decorrido:.1f}s em corpo hostil — backtracking de volta?"
    )


def test_indice_sem_script_de_params_e_quebra_de_contrato():
    from app.services.diario_oficial_service import (
        DOUIndisponivelError,
        _extrair_json_do_indice,
    )

    with pytest.raises(DOUIndisponivelError, match="contrato do portal mudou"):
        _extrair_json_do_indice("<html><body>portal reformulado</body></html>")


def test_script_de_params_malformado_nao_estoura_sem_diagnostico():
    """`id="params"` presente mas sem fechamento — erro claro, não IndexError."""
    from app.services.diario_oficial_service import (
        DOUIndisponivelError,
        _extrair_json_do_indice,
    )

    with pytest.raises(DOUIndisponivelError, match="malformado"):
        _extrair_json_do_indice('<html><script id="params"')


def test_hora_do_job_malformada_nao_derruba_o_boot():
    """Regressão P2-3: `int("11h00")` derrubava a aplicação inteira.

    `start_scheduler()` roda sem try/except no lifespan do FastAPI, então uma
    variável de ambiente malformada levava junto backup, DJEN, prazos e
    prescrição. Variável de ambiente não pode ter esse poder.
    """
    from app.services.scheduler import _hora_utc_do_job

    assert _hora_utc_do_job("07:30", padrao=(11, 0), rotulo="X") == (7, 30)
    for ruim in ("11h00", "", None, "25:00", "10:99", "abc", "12"):
        assert _hora_utc_do_job(ruim, padrao=(11, 0), rotulo="X") == (11, 0)


def test_email_do_dou_escapa_conteudo_de_terceiro():
    """Regressão P3-2: título e link vêm do portal e iam crus para MIMEText."""
    from app.services.diario_oficial_service import _esc

    assert _esc("Portaria 'X' & <b>Y</b>") == (
        "Portaria &#x27;X&#x27; &amp; &lt;b&gt;Y&lt;/b&gt;"
    )
    assert _esc(None) == ""
