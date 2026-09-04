"""Regressões do auditor histórico WORM do módulo Clientes."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from scripts.auditar_clientes_worm_pii import detectar_riscos, resumir_log


def test_detector_classifica_pii_sem_precisar_expor_valor():
    riscos = detectar_riscos({
        "cpf": "111.444.777-35",
        "contato": "pessoa@example.com",
        "observacao_tecnica": "registro interno",
    })
    assert "CAMPO:cpf" in riscos
    assert "CPF" in riscos
    assert "EMAIL" in riscos


def test_uuid_tecnico_nao_e_tratado_como_pii_por_si_so():
    riscos = detectar_riscos("registro 123e4567-e89b-12d3-a456-426614174000")
    assert riscos == set()


def test_resumo_nao_ecoa_conteudo_sensivel():
    cpf = "111.444.777-35"
    email = "pessoa@example.com"
    log = SimpleNamespace(
        id="audit-1",
        registro_id="cliente-1",
        entidade="clients",
        acao="UPDATE",
        created_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        detalhes=f"ajuste solicitado por {email}",
        dados_antes={"cpf": cpf},
        dados_depois={"status": "ativo"},
    )

    resumo = resumir_log(log)
    assert resumo is not None
    serializado = json.dumps(resumo, ensure_ascii=False)
    assert cpf not in serializado
    assert email not in serializado
    assert resumo["audit_log_id"] == "audit-1"
    assert "CPF" in resumo["riscos"]
    assert "EMAIL" in resumo["riscos"]
