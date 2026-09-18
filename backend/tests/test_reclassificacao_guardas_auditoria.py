"""Correções P2-5 e P2-6 no script scripts/reclassificar_areas_casos.py.

P2-5 — detecção de produção tinha ponto cego: no modo que o próprio runbook
       oferece (rodar no host com DATABASE_URL_SYNC exportada), os três sinais
       falhavam juntos e, com --sem-interacao --confirmo-backup, a camada sumia.
P2-6 — o arquivo de rollback era confiado sem integridade e gravado com umask
       padrão: quem escrevesse no diretório dirigia UPDATEs em `cases`.
"""
from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[2]


def _carregar():
    caminho = _RAIZ / "scripts" / "reclassificar_areas_casos.py"
    spec = importlib.util.spec_from_file_location("reclassificar_areas_casos", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def script(monkeypatch):
    monkeypatch.setenv("EJC_ROLLBACK_HMAC_KEY", "chave-de-teste-com-16-mais")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("EJC_NAO_E_PRODUCAO", raising=False)
    return _carregar()


# ══════════════════════════════════════════════════════════════════════════
# P2-5 — assume produção salvo negação explícita
# ══════════════════════════════════════════════════════════════════════════
def test_p2_5_cenario_do_runbook_agora_e_tratado_como_producao(script):
    """Host local + banco `ejc_db` + sem APP_ENV: exatamente o modo do runbook,
    onde os três sinais antigos falhavam juntos."""
    prod, motivo = script.parece_producao("postgresql://u:s@localhost:5432/ejc_db")
    assert prod is True
    assert "precaução" in motivo


@pytest.mark.parametrize("url", [
    "postgresql://u:s@localhost:5432/ejc_db",
    "postgresql://u:s@127.0.0.1:5432/qualquer",
    "postgresql://u:s@db:5432/ejc",
])
def test_p2_5_default_e_producao(script, url):
    assert script.parece_producao(url)[0] is True


def test_p2_5_negacao_explicita_por_app_env(script, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert script.parece_producao("postgresql://u:s@localhost:5432/ejc_db")[0] is False


def test_p2_5_negacao_explicita_por_flag(script, monkeypatch):
    monkeypatch.setenv("EJC_NAO_E_PRODUCAO", "1")
    assert script.parece_producao("postgresql://u:s@localhost:5432/ejc_db")[0] is False


def test_p2_5_producao_declarada_continua_detectada(script, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    prod, motivo = script.parece_producao("postgresql://u:s@localhost:5432/x")
    assert prod is True and "APP_ENV" in motivo


def test_p2_5_flag_existe_no_cli(script):
    parser = script.construir_parser()
    opcoes = {a.dest for a in parser._actions}
    assert "nao_e_producao" in opcoes


# ══════════════════════════════════════════════════════════════════════════
# P2-6 — integridade, validação de conteúdo e permissões do rollback
# ══════════════════════════════════════════════════════════════════════════
def _payload(case_id="6f1b0f6e-1f5a-4c2e-9a6a-2b7c8d9e0f11",
             anterior="civil", nova="imobiliario"):
    return {
        "tipo": "reclassificacao_area_cases",
        "itens": [{"case_id": case_id, "area_anterior": anterior, "area_nova": nova}],
    }


def test_p2_6_arquivo_gravado_com_permissao_restrita(script, tmp_path):
    alvo = tmp_path / "sub" / "rollback.json"
    script.gravar_rollback(alvo, _payload())
    assert stat.S_IMODE(alvo.stat().st_mode) == 0o600
    assert stat.S_IMODE(alvo.parent.stat().st_mode) == 0o700


def test_p2_6_arquivo_e_assinado_e_le_de_volta(script, tmp_path):
    alvo = tmp_path / "rollback.json"
    script.gravar_rollback(alvo, _payload())
    conteudo = json.loads(alvo.read_text(encoding="utf-8"))
    assert conteudo["assinatura"]["alg"] == "HMAC-SHA256"
    assert script.ler_rollback(alvo)["itens"]          # round-trip válido


def test_p2_6_conteudo_adulterado_e_recusado(script, tmp_path):
    """Cenário do auditor: terceiro edita o JSON plantado para redirecionar o UPDATE."""
    alvo = tmp_path / "rollback.json"
    script.gravar_rollback(alvo, _payload())
    conteudo = json.loads(alvo.read_text(encoding="utf-8"))
    conteudo["itens"][0]["area_nova"] = "tributario"   # adultera após a assinatura
    alvo.write_text(json.dumps(conteudo), encoding="utf-8")
    with pytest.raises(SystemExit, match="Assinatura INVÁLIDA"):
        script.ler_rollback(alvo)


def test_p2_6_arquivo_sem_assinatura_e_recusado(script, tmp_path):
    alvo = tmp_path / "plantado.json"
    alvo.write_text(json.dumps(_payload()), encoding="utf-8")
    with pytest.raises(SystemExit, match="assinatura de integridade"):
        script.ler_rollback(alvo)


def test_p2_6_case_id_nao_uuid_e_recusado(script, tmp_path):
    alvo = tmp_path / "rollback.json"
    script.gravar_rollback(alvo, _payload(case_id="'; DROP TABLE cases; --"))
    with pytest.raises(SystemExit, match="case_id inválido"):
        script.ler_rollback(alvo)


def test_p2_6_area_fora_do_enum_e_recusada(script, tmp_path):
    alvo = tmp_path / "rollback.json"
    script.gravar_rollback(alvo, _payload(nova="area_inventada"))
    with pytest.raises(SystemExit, match="não pertence"):
        script.ler_rollback(alvo)


def test_p2_6_dominio_de_areas_vem_da_fonte_da_verdade(script):
    """O conjunto é DERIVADO do enum do backend — lista transcrita à mão
    divergiria e rejeitaria área legítima."""
    from app.models.case import CaseArea

    assert script.AREAS_CASEAREA == {e.value for e in CaseArea}
    assert len(script.AREAS_CASEAREA) == 25


def test_p2_6_sem_chave_hmac_recusa_gravar(monkeypatch, tmp_path):
    monkeypatch.delenv("EJC_ROLLBACK_HMAC_KEY", raising=False)
    monkeypatch.setenv("SECRET_KEY", "curta")
    mod = _carregar()
    with pytest.raises(SystemExit, match="Assinatura do rollback indisponível"):
        mod.gravar_rollback(tmp_path / "x.json", _payload())


def test_p2_6_runbook_orienta_expurgo_do_arquivo():
    runbook = _RAIZ / "RUNBOOK_RECLASSIFICACAO_AREAS.md"
    if not runbook.is_file():
        pytest.skip("runbook ausente neste checkout")
    texto = runbook.read_text(encoding="utf-8").lower()
    assert "expurg" in texto or "remova o arquivo" in texto or "shred" in texto
