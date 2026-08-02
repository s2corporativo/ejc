"""Bloco 2 — desobstruir o caminho da peça até o protocolo.

Três mudanças, três riscos distintos a travar:

1. `POST /{id}/conferir-e-assinar` consolida validar → marcar HITL → aprovar em
   um ato. O risco é a consolidação virar afrouxamento: sumir com os gates de
   qualidade, com a exigência de observações, ou com o registro de quem assinou.
   A Lei 8.906/94, art. 32 responsabiliza o advogado pela peça — consolidar
   ETAPAS é o objetivo; apagar o RASTRO não é.

2. `GET /{id}/pdf-minuta` libera a leitura antes da assinatura. O risco é o
   inverso: virar uma porta lateral para tirar PDF de protocolo sem passar pelos
   gates. Ele tem de sair sempre marcado como minuta.

3. O rótulo de `rascunho` mudou. O risco é alguém "arrumar" o VALOR do enum
   junto — o que quebraria o banco, já que a coluna é ENUM nativo.

Segue o padrão de `test_legal_doc_flow_contract.py`: inspeção de fonte para
invariantes estruturais, que é o que o repositório usa para este router.
"""
from pathlib import Path


def _source(path: str) -> str:
    return (Path(__file__).parents[1] / path).read_text(encoding="utf-8")


def _function_source(source: str, name: str) -> str:
    start = source.index(f"async def {name}(")
    tail = source[start:]
    marker = tail.find("\n\n@router.")
    return tail if marker < 0 else tail[:marker]


# ── 1. Conferir e assinar ────────────────────────────────────────────────────


def test_conferir_e_assinar_existe_e_e_um_post():
    src = _source("app/routers/legal_docs.py")
    assert '@router.post("/{doc_id}/conferir-e-assinar")' in src


def test_conferir_e_assinar_mantem_os_dois_gates_de_qualidade():
    """Os MESMOS gates do /aprovar. Consolidar não pode baixar a régua."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "_bloquear_sem_validacao" in bloco
    assert "_bloquear_jurisprudencia_nao_validada" in bloco


def test_conferir_e_assinar_exige_observacoes_para_peca_de_ia():
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "d.ai_generated and not observacoes" in bloco
    assert "status_code=422" in bloco


def test_conferir_e_assinar_registra_quem_quando_e_sobre_qual_versao():
    """O rastro do ato profissional — Lei 8.906/94, art. 32."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "d.revisor_id = cu.id" in bloco
    assert "d.revisado_em = datetime.now(timezone.utc)" in bloco
    assert "d.notas_revisao = observacoes" in bloco
    assert 'criar_audit_log' in bloco
    assert '"APROVAR_HITL"' in bloco


def test_conferir_e_assinar_usa_lock_pessimista():
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert ".with_for_update()" in bloco


def test_conferir_e_assinar_grava_tudo_em_uma_transacao():
    """Um único commit, no fim.

    Gravação em dois lugares sem transação é a classe de defeito que a auditoria
    encontrou repetida cinco vezes neste código. Se aparecer um commit no meio,
    uma reprovação de gate deixaria a peça meio-assinada.
    """
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert bloco.count("await db.commit()") == 1
    corpo_antes_dos_gates = bloco[: bloco.index("_bloquear_sem_validacao")]
    assert "await db.commit()" not in corpo_antes_dos_gates, (
        "commit antes dos gates deixaria validação e HITL gravados numa peça reprovada"
    )


def test_conferir_e_assinar_reaproveita_validacao_da_versao_corrente():
    """Texto idêntico não é revalidado — o hash da migration 123 decide."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "_ultima_validacao_peca" in bloco
    assert 'validacao.get("ai_log_id") is None' in bloco


# ── 2. PDF de minuta ─────────────────────────────────────────────────────────


def test_pdf_minuta_existe():
    assert '@router.get("/{doc_id}/pdf-minuta")' in _source("app/routers/legal_docs.py")


def test_pdf_minuta_nao_e_porta_lateral_para_o_pdf_de_protocolo():
    """Sai sempre marcado como minuta, nunca como pronto para protocolo."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "exportar_pdf_minuta")
    assert "pronto_protocolo=False" in bloco
    assert "pronto_protocolo=True" not in bloco
    assert "_gates_exportacao_protocolo" not in bloco, (
        "o PDF de leitura não passa pelos gates de protocolo — e por isso NÃO "
        "pode sair com a marca de protocolo"
    )


def test_pdf_minuta_preserva_o_controle_de_acesso_ao_caso():
    bloco = _function_source(_source("app/routers/legal_docs.py"), "exportar_pdf_minuta")
    assert "verificar_acesso_caso" in bloco


def test_pdf_minuta_carrega_a_marca_de_ia_no_arquivo_baixado():
    bloco = _function_source(_source("app/routers/legal_docs.py"), "exportar_pdf_minuta")
    assert "minuta_ia=bool(d.ai_generated and not d.human_reviewed)" in bloco


def test_pdf_de_protocolo_continua_atras_dos_gates():
    """Regressão: a liberação da minuta não pode ter afrouxado o PDF final."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "exportar_pdf")
    assert "_gates_exportacao_protocolo" in bloco
    assert "pronto_protocolo=True" in bloco


# ── 3. Rótulo ────────────────────────────────────────────────────────────────


def test_rotulo_de_rascunho_nomeia_a_acao_pendente():
    from app.services.peca_numeracao import status_label

    assert status_label("rascunho") == "Minuta final — conferir e assinar"


def test_valor_do_enum_permanece_rascunho():
    """A coluna é ENUM nativo no Postgres: renomear o VALOR quebraria o banco."""
    from app.models.legal_doc import PecaStatus

    assert PecaStatus.rascunho.value == "rascunho"
    assert [s.value for s in PecaStatus] == [
        "rascunho", "em_revisao", "corrigida", "aprovada", "final", "protocolada",
    ]


def test_frontend_mantem_a_chave_do_enum_no_filtro_da_fila():
    """O rótulo mudou no frontend; a chave enviada ao backend, não."""
    fonte = (
        Path(__file__).parents[2] / "frontend" / "src" / "pages" / "Pecas.tsx"
    ).read_text(encoding="utf-8")
    assert 'key: "rascunho"' in fonte
    assert 'label: "Minuta final"' in fonte
