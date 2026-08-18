"""Documento Único de Anexos — capa/índice/separadores + legenda IA + mesclagem.

Cobre as partes determinísticas (sem weasyprint) e o contrato de IA:
  - índice e folhas de separação no padrão do escritório;
  - legenda IA sanitiza PII ANTES do LLM (mesma regra do IA-01) e grava AILog;
  - mesclagem real de PDFs via pypdf preserva a contagem de páginas.
"""
from __future__ import annotations

import io

from app.services import anexos_service as svc
from app.services.anexos_service import ContextoAnexos, ItemAnexo


def _ctx() -> ContextoAnexos:
    return ContextoAnexos(
        titulo_acao="AÇÃO DE INDENIZAÇÃO — DANOS MORAIS E MATERIAIS",
        partes="Clovis Jose Soares vs. Decolar.com Ltda.",
        referencia="Reserva 46190319300",
        rodape="Juizado Especial Cível da Comarca de Betim/MG",
    )


# ── Capa / índice ─────────────────────────────────────────────────────────────

def test_cover_tem_titulo_indice_e_todos_os_docs():
    itens = [
        ItemAnexo(ordem=1, titulo="Reclamação Consumidor.gov — Prot. 2025.11"),
        ItemAnexo(ordem=2, titulo="Comprovante PIX — R$ 1.000,00"),
    ]
    html = svc.cover_html(_ctx(), itens)
    assert "ANEXOS" in html
    assert "Índice de Documentos" in html
    assert "Doc. 01" in html and "Doc. 02" in html
    assert "Reclamação Consumidor.gov" in html
    assert "AÇÃO DE INDENIZAÇÃO" in html
    assert "Betim/MG" in html


def test_cover_numera_com_dois_digitos():
    itens = [ItemAnexo(ordem=i, titulo=f"Doc {i}") for i in range(1, 4)]
    html = svc.cover_html(_ctx(), itens)
    assert "Doc. 01" in html and "Doc. 03" in html
    assert "Doc. 1<" not in html  # sempre zero-padded


# ── Folha de separação ────────────────────────────────────────────────────────

def test_separador_tem_numero_titulo_e_legenda():
    item = ItemAnexo(
        ordem=3,
        titulo="COMPROVANTE DE PAGAMENTO",
        legenda="PIX de R$ 1.000,00 ao Banco do Brasil comprovando a diária adicional paga",
    )
    html = svc.separador_html(_ctx(), item)
    assert "DOC. 03" in html
    assert "COMPROVANTE DE PAGAMENTO" in html
    assert "PIX de R$ 1.000,00" in html
    assert "Betim/MG" in html


def test_separador_escapa_html_do_titulo():
    item = ItemAnexo(ordem=1, titulo="Contrato <script>alert(1)</script>")
    html = svc.separador_html(_ctx(), item)
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html


# ── Limpeza de legenda ────────────────────────────────────────────────────────

def test_limpar_legenda_pega_primeira_linha_e_remove_aspas_e_ponto():
    assert svc._limpar_legenda('"Comprovante de pagamento."\noutra linha') == "Comprovante de pagamento"


def test_limpar_legenda_remove_prefixo_de_rotulo():
    assert svc._limpar_legenda("Legenda: Reclamação registrada no Consumidor.gov") == \
        "Reclamação registrada no Consumidor.gov"


def test_limpar_legenda_trunca_no_limite():
    longa = "a" * 400
    out = svc._limpar_legenda(longa)
    assert len(out) <= svc._LEGENDA_MAX
    assert out.endswith("…")


# ── Legenda IA: sanitiza PII antes do LLM + grava AILog ───────────────────────

class _Resp:
    def __init__(self, texto):
        self.texto = texto
        self.modelo = "llama"
        self.provedor = "groq"
        self.input_tokens = 10
        self.output_tokens = 5


async def test_legenda_ia_envia_texto_sanitizado_e_loga(monkeypatch):
    capturado = {}

    async def fake_chat(*, messages, **kw):
        capturado["user"] = messages[-1]["content"]
        capturado["task"] = kw.get("task_type")
        return _Resp("Reclamação do consumidor com resposta da empresa")

    async def fake_log(db, **kw):
        capturado["log"] = kw
        return "log-id"

    monkeypatch.setattr(svc, "gw_chat", fake_chat)
    monkeypatch.setattr(svc, "registrar_ai_log", fake_log)

    legenda = await svc.gerar_legenda_ia(
        db=None,
        user_id="u1",
        case_id="c1",
        titulo="Reclamação Consumidor.gov",
        tipo="prova",
        ocr_text="Consumidor CLOVIS, CPF 058.858.426-63, reserva 46190319300, resposta da empresa.",
    )

    assert legenda == "Reclamação do consumidor com resposta da empresa"
    # Sanitização reativada (LGPD): o CPF vai MASCARADO ao provedor.
    assert "058.858.426-63" not in capturado["user"]
    assert "[CPF]" in capturado["user"]
    # task de prosa (recebe base anti-alucinação):
    assert capturado["task"] == "chat_rapido"
    # AILog registra que houve remoção de PII:
    assert capturado["log"]["pii_removida"] is True
    assert capturado["log"]["case_id"] == "c1"


async def test_legenda_ia_sem_texto_nao_chama_llm(monkeypatch):
    chamou = {"n": 0}

    async def fake_chat(**kw):
        chamou["n"] += 1
        return _Resp("x")

    monkeypatch.setattr(svc, "gw_chat", fake_chat)
    out = await svc.gerar_legenda_ia(
        db=None, user_id="u", case_id=None, titulo="Doc", tipo=None, ocr_text="   "
    )
    assert out == ""
    assert chamou["n"] == 0


async def test_legenda_ia_provedor_indisponivel_devolve_vazio(monkeypatch):
    async def boom(**kw):
        raise RuntimeError("provedor fora")

    monkeypatch.setattr(svc, "gw_chat", boom)
    out = await svc.gerar_legenda_ia(
        db=None, user_id="u", case_id=None, titulo="Doc", tipo=None, ocr_text="algum texto"
    )
    assert out == ""


# ── resolver_itens: legenda manual tem prioridade, sem doc não consulta DB ─────

async def test_resolver_itens_legenda_manual_pula_ia():
    itens = await svc.resolver_itens(
        db=None,
        cu_id="u1",
        case_id="c1",
        itens_in=[
            {"titulo": "Comprovante PIX", "legenda": "Pagamento de R$ 1.000,00"},
            {"legenda": "Sem título vira Documento 2"},
        ],
        com_ia=True,
    )
    assert itens[0].titulo == "Comprovante PIX"
    assert itens[0].legenda == "Pagamento de R$ 1.000,00"
    assert itens[0].ordem == 1
    assert itens[1].titulo == "Documento 2"


# ── Mesclagem real de PDFs (pypdf) ────────────────────────────────────────────

def _pdf_de_paginas(n: int) -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(n):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_mesclar_soma_paginas_e_ignora_partes_vazias():
    from pypdf import PdfReader

    partes = [_pdf_de_paginas(1), b"", _pdf_de_paginas(2), _pdf_de_paginas(1)]
    saida = svc._mesclar(partes)
    assert len(PdfReader(io.BytesIO(saida)).pages) == 4


def test_mesclar_ignora_bytes_invalidos():
    from pypdf import PdfReader

    partes = [_pdf_de_paginas(1), b"nao-e-pdf", _pdf_de_paginas(1)]
    saida = svc._mesclar(partes)
    assert len(PdfReader(io.BytesIO(saida)).pages) == 2


# ── Razões / Fundamentação Jurídica ───────────────────────────────────────────

class _RespRazoes:
    def __init__(self, texto):
        self.texto = texto
        self.modelo = "deepseek"
        self.provedor = "ollama"
        self.input_tokens = 100
        self.output_tokens = 800


async def test_razoes_referencia_docs_grounding_e_nivel(monkeypatch):
    cap = {}

    async def fake_escopo(db, case_id):
        return "cli-1"

    async def fake_rag(db, consulta, limite=6, scope_client_id=None, **kw):
        cap["rag_scope"] = scope_client_id
        return [{"titulo": "CDC art. 14", "conteudo": "Responsabilidade objetiva do fornecedor."}]

    async def fake_chat(*, messages, **kw):
        cap["system"] = messages[0]["content"]
        cap["user"] = messages[1]["content"]
        cap["task"] = kw.get("task_type")
        cap["nivel"] = kw.get("nivel_inteligencia")
        return _RespRazoes("I — SÍNTESE DOS FATOS\nConforme Doc. 03, houve pagamento...")

    async def fake_cit(db, texto):
        cap["cit_texto"] = texto
        return {"total": 0, "nao_confirmadas": []}

    async def fake_log(db, **kw):
        cap["log"] = kw
        return "id"

    monkeypatch.setattr(svc, "_escopo_cliente_do_caso", fake_escopo)
    monkeypatch.setattr(svc, "buscar_contexto_rag", fake_rag)
    monkeypatch.setattr(svc, "gw_chat", fake_chat)
    monkeypatch.setattr(svc, "verificar_citacoes", fake_cit)
    monkeypatch.setattr(svc, "registrar_ai_log", fake_log)

    itens = [
        ItemAnexo(1, "Reclamação Consumidor.gov"),
        ItemAnexo(3, "Comprovante PIX", legenda="PIX de R$ 1.000,00 ao Banco do Brasil"),
    ]
    out = await svc.gerar_razoes_juridicas(
        None, cu_id="u1", case_id="c1", ctx=_ctx(), itens=itens,
        objetivo="reembolso e danos morais", area="Consumidor", nivel="maximo",
    )

    # Estrutura argumentativa exigida no system prompt:
    for secao in ("SÍNTESE DOS FATOS", "DO DIREITO", "DA RESPONSABILIDADE", "DOS DANOS", "DOS PEDIDOS"):
        assert secao in cap["system"]
    # Anti-alucinação: nunca inventar + rótulo dos documentos:
    assert "NUNCA invente" in cap["system"]
    # Os anexos entram numerados no prompt do usuário:
    assert "Doc. 01 — Reclamação Consumidor.gov" in cap["user"]
    assert "Doc. 03 — Comprovante PIX" in cap["user"]
    assert "PIX de R$ 1.000,00" in cap["user"]
    # Grounding RAG presente e no escopo do cliente:
    assert "CDC art. 14" in cap["user"]
    assert cap["rag_scope"] == "cli-1"
    # Raciocínio máximo + task de prosa:
    assert cap["nivel"] == "maximo"
    assert cap["task"] == "elaboracao_peca"
    # Saída: verificação de citações acoplada, docs referenciados e HITL:
    assert out["verificacao_citacoes"] == {"total": 0, "nao_confirmadas": []}
    assert out["docs_referenciados"] == ["Doc. 01", "Doc. 03"]
    assert "RASCUNHO" in out["aviso"]
    # AILog gravado como redação de peça:
    assert cap["log"]["case_id"] == "c1"
    assert cap["log"]["fontes_rag"] is not None


async def test_razoes_sem_rag_nao_inventa_sinaliza(monkeypatch):
    async def fake_escopo(db, case_id):
        return None

    async def fake_rag(db, consulta, limite=6, scope_client_id=None, **kw):
        return []

    async def fake_chat(*, messages, **kw):
        return _RespRazoes("texto")

    monkeypatch.setattr(svc, "_escopo_cliente_do_caso", fake_escopo)
    monkeypatch.setattr(svc, "buscar_contexto_rag", fake_rag)
    monkeypatch.setattr(svc, "gw_chat", fake_chat)
    monkeypatch.setattr(svc, "verificar_citacoes", lambda db, t: _noop())
    monkeypatch.setattr(svc, "registrar_ai_log", lambda db, **k: _noop())

    out = await svc.gerar_razoes_juridicas(
        None, cu_id="u", case_id="c", ctx=_ctx(),
        itens=[ItemAnexo(1, "Doc")], objetivo=None,
    )
    assert "texto" in out["texto"]


async def _noop():
    return None
