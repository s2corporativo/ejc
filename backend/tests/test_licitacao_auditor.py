# ── tests/test_licitacao_auditor.py ───────────────────────────────────────────
# Motor de regras deterministico do auditor de licitacoes (Lei 14.133/21).
# _aplicar_regras e puro (texto -> achados), entao testa-se sem PDF nem rede.
from app.core.licitacao_auditor import LicitacaoAuditor, _norm, REGRAS


def _regras(texto):
    return LicitacaoAuditor._aplicar_regras(texto)


def test_texto_limpo_nao_gera_achados():
    r = _regras("Proposta regular, com todos os documentos de habilitacao anexados.")
    assert r["falha"] == [] and r["equivalencia"] == []


def test_regra_anvisa_dispara_com_e_sem_acento():
    # A normalizacao colapsa 'certificação' e 'certificacao' na mesma regra.
    for t in ("Produto SEM CERTIFICAÇÃO ANVISA no lote.",
              "produto sem certificacao anvisa"):
        r = _regras(t)
        assert any("ANVISA" in m for m in r["falha"]), t


def test_similar_sem_equivalencia_vira_equivalencia():
    r = _regras("Ofertamos produto similar ao especificado.")
    assert len(r["equivalencia"]) == 1
    assert r["falha"] == []


def test_similar_com_laudo_nao_falso_positivo():
    """Excludente: se a propria proposta traz laudo/equivalencia comprovada,
    a regra de 'similar' NAO deve disparar."""
    r = _regras("Produto similar, com laudo de equivalencia tecnica anexo (equivalencia comprovada).")
    assert r["equivalencia"] == []


def test_regularidade_fiscal_positiva_com_efeito_negativa_nao_dispara():
    r = _regras("Apresenta certidao positiva com efeito de negativa, valida.")
    assert all("irregularidade" not in m.lower() for m in r["falha"])


def test_multiplos_achados_acumulam():
    texto = (
        "Produto sem certificacao anvisa. "
        "Prazo de entrega superior a 60 dias. "
        "Menciona subcontratacao de parte do objeto."
    )
    r = _regras(texto)
    assert len(r["falha"]) >= 3


def test_me_epp_sinaliza_beneficio():
    r = _regras("Declaramos enquadramento como microempresa (ME/EPP).")
    assert any("ME/EPP" in m or "beneficio" in m.lower() for m in r["falha"])


def test_norm_remove_acentos_e_caixa():
    assert _norm("Equivalência TÉCNICA") == "equivalencia tecnica"


def test_todas_as_regras_tem_id_unico_e_bucket_valido():
    ids = [r.id for r in REGRAS]
    assert len(ids) == len(set(ids)), "ids de regra duplicados"
    assert all(r.bucket in ("falha", "equivalencia") for r in REGRAS)


# ── Camada de IA opt-in (LGPD-safe): sanitiza → gateway → AILog → degrada ──────
class _FakeResp:
    texto = '{"pontos": ["Falta atestado tecnico"], "equivalencia": ["Similar sem laudo"]}'
    provedor = "ollama"
    modelo = "llama3"
    input_tokens = 10
    output_tokens = 20
    custo_estimado_brl = 0.0


def _mock_ia(monkeypatch, *, chat_resp=None, chat_erro=None):
    """Substitui gateway.chat, registrar_ai_log e sanitizar_pii. Retorna um dict
    de flags para o teste inspecionar o que foi registrado."""
    estado = {"log_chamado": False, "sanitizou": False}

    async def _chat(**_kw):
        if chat_erro:
            raise chat_erro
        return chat_resp or _FakeResp()

    async def _log(db, **_kw):
        estado["log_chamado"] = True
        return "log-id-123"

    def _sanit(texto, *a, **k):
        estado["sanitizou"] = True
        return texto, False

    monkeypatch.setattr("app.services.ai_gateway.chat", _chat)
    monkeypatch.setattr("app.services.ai_guard.registrar_ai_log", _log)
    monkeypatch.setattr("app.services.sanitizer.sanitizar_pii", _sanit)
    return estado


async def test_enriquecer_com_ia_parseia_e_audita(monkeypatch):
    estado = _mock_ia(monkeypatch)
    out = await LicitacaoAuditor()._enriquecer_com_ia("texto da proposta", db=object(), user_id="u1")
    assert out["pontos"] == ["Falta atestado tecnico"]
    assert out["equivalencia"] == ["Similar sem laudo"]
    assert estado["log_chamado"] is True      # AILog obrigatorio (art. 37 LGPD)
    assert estado["sanitizou"] is True         # sanitizacao antes do LLM


async def test_analyze_com_ia_mescla_flags(monkeypatch):
    _mock_ia(monkeypatch)
    aud = LicitacaoAuditor()
    monkeypatch.setattr(aud, "_extract_text_from_pdf",
                        lambda _b: "Proposta com texto suficiente para acionar a IA. " * 3)
    r = await aud.analyze_competitor_proposal(b"pdf", db=object(), user_id="u1", com_ia=True)
    assert r["ia_usada"] is True
    assert r["ai_flags"] == ["Falta atestado tecnico"]
    assert "MINUTA" in r["aviso"]


async def test_analyze_com_ia_degrada_quando_gateway_falha(monkeypatch):
    _mock_ia(monkeypatch, chat_erro=RuntimeError("gateway fora"))
    aud = LicitacaoAuditor()
    monkeypatch.setattr(aud, "_extract_text_from_pdf",
                        lambda _b: "Texto suficiente para tentar a IA e falhar. " * 3)
    r = await aud.analyze_competitor_proposal(b"pdf", db=object(), user_id="u1", com_ia=True)
    assert r.get("ia_indisponivel") is True
    assert r["ia_usada"] is False              # deterministico intacto
    assert "potential_flaws" in r


async def test_analyze_sem_ia_nao_toca_gateway(monkeypatch):
    """com_ia=False (default) NAO chama IA — caminho deterministico puro."""
    async def _boom(**_k):
        raise AssertionError("gateway nao deveria ser chamado")
    monkeypatch.setattr("app.services.ai_gateway.chat", _boom)
    aud = LicitacaoAuditor()
    monkeypatch.setattr(aud, "_extract_text_from_pdf", lambda _b: "Produto sem certificacao anvisa. " * 3)
    r = await aud.analyze_competitor_proposal(b"pdf", db=object(), user_id="u1", com_ia=False)
    assert r["ia_usada"] is False
    assert r["ai_flags"] == []
    assert any("ANVISA" in m for m in r["potential_flaws"])
