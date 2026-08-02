"""Ingestor STJ (espelhos de acórdãos do Portal de Dados Abertos → RAG).

Foco: o conteúdo gravado precisa ser AUTOIDENTIFICÁVEL (Issue #635).

Antes da correção, `_monta_conteudo` montava classe + relator + órgão +
publicação + ementa + tese, SEM o número do processo/registro. Recursos
julgados em bloco sobre o mesmo tema (mesma classe, relator, órgão e data, com
a ementa idêntica que o STJ publica em repetitivos) geravam texto byte a byte
igual → mesmo SHA-1 em `hash_conteudo` → falso duplicado no painel de
governança; e — o problema real — o trecho recuperado pelo RAG chegava à IA sem
o próprio número do processo, condição clássica da citação inventada.

Cobre (SEM rede e SEM banco):
1) _txt: leitura tolerante de campo ausente/None/vazio.
2) _monta_conteudo: identificação (processo, registro, julgamento) no corpo,
   fallbacks de nome de campo e degradação graciosa quando tudo falta.
3) Regressão da Issue #635: mesma ementa + números diferentes → conteúdos e
   hashes (`ingestion_service._sha1` sobre `normalizar`) distintos.
4) ingerir(): o conteúdo upsertado carrega o número do processo.
"""
from __future__ import annotations

import app.services.ingestors.stj as stj
from app.services.ingestion_service import _sha1, normalizar

EMENTA_REPETITIVA = (
    "PROCESSUAL CIVIL E TRIBUTÁRIO. RECURSO ESPECIAL REPETITIVO. TESE FIRMADA "
    "SOB O RITO DOS RECURSOS REPETITIVOS. Incidência da contribuição sobre a "
    "verba discutida. Recurso conhecido e provido."
)


def _acordao(**over) -> dict:
    """Registro no shape do espelho de acórdão do CKAN do STJ."""
    base = {
        "siglaClasse": "REsp",
        "descricaoClasse": "Recurso Especial",
        "numeroProcesso": "2201422",
        "numeroRegistro": "2024/0123456-7",
        "ministroRelator": "FULANO DE TAL",
        "nomeOrgaoJulgador": "PRIMEIRA SEÇÃO",
        "dataJulgamento": "2026-03-11",
        "dataPublicacao": "2026-03-18",
        "ementa": EMENTA_REPETITIVA,
        "teseJuridica": "A contribuição incide sobre a verba discutida.",
        "tema": "1234",
        "referenciasLegislativas": ["LEG:FED LEI:008212 ANO:1991 ART:00028"],
    }
    base.update(over)
    return base


def _hash(rec: dict) -> str:
    """Mesmo caminho do upsert: normalizar() → _sha1() = `hash_conteudo`."""
    return _sha1(normalizar(stj._monta_conteudo(rec)))


# ── 1. _txt (leitura tolerante) ───────────────────────────────────────────────

def test_txt_primeiro_valor_nao_vazio_e_degrada():
    rec = {"a": None, "b": "  ", "c": "valor", "d": "outro"}
    assert stj._txt(rec, "a", "b", "c", "d") == "valor"
    assert stj._txt(rec, "inexistente") == ""
    assert stj._txt({}, "x", "y") == ""
    # o CKAN às vezes devolve a string "None"; ela não pode virar corpo do doc
    assert stj._txt({"x": "None"}, "x") == ""
    # valor não-string (número) é aceito e convertido
    assert stj._txt({"x": 2201422}, "x") == "2201422"


# ── 2. _monta_conteudo (identificação no corpo) ───────────────────────────────

def test_conteudo_carrega_numero_do_processo_registro_e_julgamento():
    txt = stj._monta_conteudo(_acordao())
    assert "2201422" in txt                       # número do processo no CORPO
    assert "Processo: REsp 2201422" in txt        # com a classe, citável
    assert "Registro: 2024/0123456-7" in txt
    assert "Julgamento: 2026-03-11" in txt
    # e o conteúdo jurídico anterior segue presente
    assert "EMENTA:" in txt and "REPETITIVO" in txt
    assert "TESE JURÍDICA:" in txt
    assert "Relator: Min. FULANO DE TAL" in txt
    assert "Órgão: PRIMEIRA SEÇÃO" in txt
    assert "Publicação: 2026-03-18" in txt
    assert "Tema: 1234" in txt
    assert "Referências legislativas: LEG:FED LEI:008212" in txt


def test_identificacao_abre_o_conteudo():
    """A identificação vem antes da ementa: no chunking, o primeiro trecho —
    o mais recuperado — já nasce autoidentificável."""
    txt = stj._monta_conteudo(_acordao())
    assert txt.index("Processo:") < txt.index("EMENTA:")
    assert txt.startswith("Processo: REsp 2201422")


def test_fallbacks_de_nome_de_campo():
    # sem dataJulgamento → cai em dataDecisao; sem numeroProcesso → numeroUnico
    txt = stj._monta_conteudo(_acordao(
        dataJulgamento=None, dataDecisao="2026-02-02",
        numeroProcesso="", numeroUnicoProcesso="0001234-56.2024.3.00.0000",
    ))
    assert "Julgamento: 2026-02-02" in txt
    assert "Processo: REsp 0001234-56.2024.3.00.0000" in txt


def test_registro_sem_identificacao_nao_quebra():
    """Espelho sem processo, registro nem datas: o ingestor não pode quebrar
    nem escrever rótulo vazio/None — só omite o que não veio."""
    txt = stj._monta_conteudo({"ementa": EMENTA_REPETITIVA})
    assert "EMENTA:" in txt and "REPETITIVO" in txt
    assert "Processo:" not in txt and "Registro:" not in txt
    assert "Julgamento:" not in txt
    assert "None" not in txt

    # registro completamente vazio também não estoura
    assert stj._monta_conteudo({}) == ""
    assert stj._monta_conteudo({"numeroProcesso": None, "ementa": None}) == ""


def test_conteudo_sem_classe_usa_apenas_o_numero():
    txt = stj._monta_conteudo({"numeroProcesso": "2201422", "ementa": "x" * 60})
    assert "Processo: 2201422" in txt          # sem sigla, sem espaço sobrando


# ── 3. Regressão Issue #635 (falso duplicado / citação sem identificação) ─────

def test_mesma_ementa_numeros_diferentes_geram_conteudos_e_hashes_distintos():
    """Os três REsp do achado da auditoria: julgados em bloco, mesma classe,
    relator, órgão, data e ementa — só o número muda. Antes da correção o
    conteúdo era idêntico e o SHA-1 colidia."""
    a = _acordao(numeroProcesso="2201422", numeroRegistro="2024/0000001-1")
    b = _acordao(numeroProcesso="2200477", numeroRegistro="2024/0000002-2")
    c = _acordao(numeroProcesso="2205262", numeroRegistro="2024/0000003-3")

    conteudos = [stj._monta_conteudo(x) for x in (a, b, c)]
    assert len(set(conteudos)) == 3, "conteúdos ainda colidem entre si"
    assert len({_hash(x) for x in (a, b, c)}) == 3, "hash_conteudo ainda colide"

    # cada trecho carrega o PRÓPRIO número — é isso que barra citação inventada
    assert "2201422" in conteudos[0] and "2200477" not in conteudos[0]
    assert "2200477" in conteudos[1]
    assert "2205262" in conteudos[2]


def test_mesmo_acordao_mantem_hash_estavel_entre_execucoes():
    """Idempotência: sem mudança na origem, o hash não muda (senão toda
    reingestão viraria 'atualizado' e reprocessaria embeddings à toa)."""
    assert _hash(_acordao()) == _hash(_acordao())


# ── 4. ingerir() — sem rede, sem banco ────────────────────────────────────────

class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


async def test_ingerir_grava_conteudo_com_numero_do_processo(monkeypatch):
    dados = [
        _acordao(numeroProcesso="2201422", numeroRegistro="2024/0000001-1"),
        _acordao(numeroProcesso="2200477", numeroRegistro="2024/0000002-2"),
        _acordao(ementa="", numeroProcesso="9999999"),   # sem ementa → ignorado
    ]
    pacote = {"result": {"resources": [
        {"format": "CSV", "name": "20260101.csv", "url": "http://x/csv"},
        {"format": "JSON", "name": "20260101.json", "url": "http://x/a.json"},
        {"format": "json", "name": "20260201.json", "url": "http://x/b.json"},
    ]}}

    urls: list[str] = []

    async def fake_fetch(url, params=None, timeout=30, **kw):
        urls.append(url)
        if url.endswith("/package_show"):
            return _FakeResp(pacote)
        return _FakeResp(dados)

    ups: list[dict] = []

    async def fake_upsert(db, **kwargs):
        ups.append(kwargs)
        return "novo"

    monkeypatch.setattr(stj, "ORGAOS", ["espelhos-de-acordaos-primeira-secao"])
    monkeypatch.setattr(stj, "fetch", fake_fetch)
    monkeypatch.setattr(stj, "upsert_documento", fake_upsert)

    novos, total = await stj.ingerir(_FakeDB())

    assert (novos, total) == (2, 2)              # o registro sem ementa não conta
    assert urls[-1] == "http://x/b.json"         # pega o JSON mais recente
    assert len(ups) == 2
    conteudos = [u["conteudo"] for u in ups]
    assert "2201422" in conteudos[0] and "2200477" in conteudos[1]
    assert len({_sha1(normalizar(c)) for c in conteudos}) == 2
    # governança da fonte preservada
    assert all(u["categoria"] == "jurisprudencia" for u in ups)
    assert all(u["tribunal"] == "STJ" for u in ups)
    assert all(u["confianca"] == "alta" for u in ups)
    assert {u["chave_origem"] for u in ups} == {
        "stj:2024/0000001-1", "stj:2024/0000002-2",
    }
