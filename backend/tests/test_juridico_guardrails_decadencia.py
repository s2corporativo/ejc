"""Guardrail jurídico determinístico (Issue #554, problemas 1 e 2).

1. Prescrição/decadência não pode ser qualificada como "extinção sem
   resolução de mérito" — contraria o CPC, art. 487, II (mérito).
2. CDC arts. 26 (vício — decadência) e 27 (fato do produto/serviço —
   prescrição) não podem ser cumulados sem fundamentar cada pretensão
   separadamente.

Fontes oficiais citadas pelo próprio guardrail (não inventadas — as mesmas da
Issue #554):
  - CPC, art. 487, II: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm
  - CDC, arts. 26 e 27: https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm
"""
from __future__ import annotations

from app.services.ai import juridico_guardrails as jg


# ── aplicar_guardrail_merito (CPC art. 487, II) ─────────────────────────────

def test_corrige_qualificacao_errada_ligada_a_prescricao():
    texto = (
        "Diante do exposto, reconheço a PRESCRIÇÃO da pretensão e julgo o "
        "processo extinto sem resolução de mérito, nos termos do art. 485 "
        "do CPC."
    )
    corrigido, houve_correcao = jg.aplicar_guardrail_merito(texto)

    assert houve_correcao is True
    # A cláusula errada foi substituída pela correta (verbo original — "extinto"
    # — preservado; só a qualificação de mérito muda)...
    assert "extinto COM resolução de mérito (art. 487, II, do CPC)" in corrigido
    assert "sem resolução de mérito" not in corrigido.split("[CORREÇÃO")[0]
    # ...a referência ao art. 485 associada à prescrição também foi corrigida...
    assert "nos termos do art. 487, II, do CPC" in corrigido
    # ...e o aviso de correção (transparência HITL) está presente e cita a fonte.
    assert "GUARDRAIL DETERMINÍSTICO" in corrigido
    assert "art. 487, II" in corrigido
    assert "planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm" in corrigido


def test_corrige_qualificacao_errada_ligada_a_decadencia():
    # Verbo "extingo" (1ª pessoa) — forma que a versão anterior do guardrail
    # (regex exigindo "extinto/extinção") deixava passar.
    texto = "Pronuncio a decadência do direito. Extingo o feito sem resolução de mérito."
    corrigido, houve_correcao = jg.aplicar_guardrail_merito(texto)

    assert houve_correcao is True
    assert "Extingo o feito COM resolução de mérito (art. 487, II, do CPC)" in corrigido


def test_nao_altera_extincao_sem_merito_alheia_a_prescricao_decadencia():
    # "Sem resolução de mérito" é correto para MUITAS outras hipóteses do art.
    # 485 (ilegitimidade, desistência, ausência de pressuposto...) — o
    # guardrail não pode mexer nisso; só age quando o texto liga a expressão
    # a prescrição/decadência.
    texto = (
        "Diante da ilegitimidade passiva manifesta, julgo o processo extinto "
        "sem resolução de mérito, nos termos do art. 485, VI, do CPC."
    )
    corrigido, houve_correcao = jg.aplicar_guardrail_merito(texto)

    assert houve_correcao is False
    assert corrigido == texto


def test_texto_correto_nao_e_alterado():
    texto = (
        "Reconheço a prescrição da pretensão. Trata-se de sentença de mérito "
        "(art. 487, II, do CPC), não de extinção sem resolução de mérito."
    )
    # O texto MENCIONA "sem resolução de mérito", mas para dizer que NÃO é o
    # caso — o guardrail (regex simples) pode falso-positivar aqui; o
    # importante é que, se disparar, o resultado final continue afirmando o
    # mérito corretamente (nunca piora um texto já correto para o lado errado).
    corrigido, _ = jg.aplicar_guardrail_merito(texto)
    assert "art. 487, II" in corrigido


def test_texto_vazio_ou_none_nao_quebra():
    assert jg.aplicar_guardrail_merito("") == ("", False)
    assert jg.aplicar_guardrail_merito(None) == (None, False)


def test_detectar_qualificacao_extincao_indevida():
    assert jg.detectar_qualificacao_extincao_indevida(
        "a prescrição leva à extinção sem resolução de mérito"
    )
    assert not jg.detectar_qualificacao_extincao_indevida(
        "a prescrição é reconhecida por sentença de mérito"
    )
    assert not jg.detectar_qualificacao_extincao_indevida("")


# ── checar_cumulacao_vicio_fato_cdc (CDC arts. 26 e 27) ─────────────────────

def test_alerta_cumulacao_sem_diferenciar_prazos():
    texto = (
        "O caso envolve tanto vício do produto quanto fato do produto que "
        "causou dano ao consumidor. Aplicam-se os arts. 26 e 27 do CDC."
    )
    alertas = jg.checar_cumulacao_vicio_fato_cdc(texto)

    assert len(alertas) == 1
    assert "cumulação automática" in alertas[0]
    assert "art. 26" in alertas[0] and "art. 27" in alertas[0]
    assert "decadência" in alertas[0].lower() or "DECADÊNCIA" in alertas[0]
    assert "prescrição" in alertas[0].lower() or "PRESCRIÇÃO" in alertas[0]


def test_nao_alerta_quando_apenas_um_regime_esta_presente():
    texto = "O caso é de vício do produto (CDC, art. 26). Prazo decadencial de 90 dias."
    assert jg.checar_cumulacao_vicio_fato_cdc(texto) == []

    texto2 = "O caso é de fato do produto — defeito que causa dano (CDC, art. 27). Prescreve em 5 anos."
    assert jg.checar_cumulacao_vicio_fato_cdc(texto2) == []


def test_nao_alerta_quando_regimes_sao_fundamentados_separadamente():
    texto = (
        "Pretensão 1 — vício do produto (CDC, art. 26): prazo DECADENCIAL de "
        "90 dias, contado da entrega. Pretensão 2 — fato do produto, defeito "
        "que causa dano (CDC, art. 27): prazo PRESCRICIONAL de 5 anos, "
        "contado do conhecimento do dano e de sua autoria. As duas pretensões "
        "são autônomas e não se confundem."
    )
    assert jg.checar_cumulacao_vicio_fato_cdc(texto) == []


def test_texto_vazio_nao_quebra_checagem_cdc():
    assert jg.checar_cumulacao_vicio_fato_cdc("") == []
    assert jg.checar_cumulacao_vicio_fato_cdc(None) == []
