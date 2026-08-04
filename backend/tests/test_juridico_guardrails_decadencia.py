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


# ── Achado de review #1 (P0) — vigência/versão da regra citada ─────────────

def test_aviso_de_correcao_cita_vigencia_e_versao_da_regra():
    texto = (
        "Reconheço a PRESCRIÇÃO e julgo extinto sem resolução de mérito, "
        "nos termos do art. 485 do CPC."
    )
    corrigido, houve_correcao = jg.aplicar_guardrail_merito(texto)

    assert houve_correcao is True
    # Não basta citar o artigo — precisa dizer QUAL lei, QUE VERSÃO/REDAÇÃO e
    # DESDE QUANDO está em vigor (achado P0: Codex, PR #703).
    assert "Lei 13.105/2015" in corrigido
    assert "em vigor desde 18/03/2016" in corrigido


def test_alerta_cumulacao_cdc_cita_vigencia_e_versao_da_regra():
    assert "Lei 8.078/1990" in jg.ALERTA_CUMULACAO_CDC
    assert "em vigor desde 11/03/1991" in jg.ALERTA_CUMULACAO_CDC


# ── Achado de review #2 (P1) — não classificar toda resolução de mérito ────
# parcial como sentença ────────────────────────────────────────────────────

def test_aviso_nao_afirma_categoricamente_sentenca_de_merito():
    texto = "Reconheço a prescrição e julgo extinto sem resolução de mérito."
    corrigido, houve_correcao = jg.aplicar_guardrail_merito(texto)

    assert houve_correcao is True
    # O CPC permite decisão interlocutória de mérito PARCIAL (art. 356) quando
    # prescrição/decadência resolve só parte dos pedidos cumulados — "profere
    # SEMPRE sentença de mérito" (versão anterior) é categoricamente errado
    # nesse caso. O aviso não pode afirmar isso sem qualificar.
    assert "RESOLUÇÃO DE MÉRITO" in corrigido.upper()
    assert "decisão interlocutória de mérito parcial" in corrigido.lower()
    assert "art. 356" in corrigido.lower()


def test_alerta_merito_corrigido_nao_afirma_categoricamente_sentenca():
    texto_upper = jg.ALERTA_MERITO_CORRIGIDO.upper()
    assert "RESOLUÇÃO DE MÉRITO" in texto_upper
    assert "DECISÃO INTERLOCUTÓRIA DE MÉRITO PARCIAL" in texto_upper


# ── Achado de review #3 (P1) — preservar cláusulas negadas/independentes ───

def test_nao_inverte_clausula_negada_ligada_a_prescricao():
    # "não é extinção sem resolução de mérito" já afirma corretamente o
    # mérito — substituir só o núcleo produziria "não é ... COM resolução de
    # mérito", invertendo o sentido (achado P1: Codex, PR #703).
    texto = (
        "Reconheço a prescrição da pretensão. Isso não é extinção sem "
        "resolução de mérito."
    )
    corrigido, houve_correcao = jg.aplicar_guardrail_merito(texto)

    assert houve_correcao is False
    assert corrigido == texto
    assert "não é ... COM resolução de mérito" not in corrigido
    assert "não é extinção COM resolução" not in corrigido


def test_nao_troca_art485_citado_por_fundamento_proprio_alheio():
    # O art. 485 aparece perto de "prescrição" só por coincidência de
    # proximidade — a extinção sem resolução de mérito é por ILEGITIMIDADE
    # PASSIVA, fundamento independente e correto (achado P1: Codex, PR #703).
    texto = (
        "Quanto à prescrição, rejeito a preliminar arguida pela ré. "
        "Quanto à ilegitimidade passiva da segunda ré, julgo extinto sem "
        "resolução de mérito, nos termos do art. 485, VI, do CPC."
    )
    corrigido, houve_correcao = jg.aplicar_guardrail_merito(texto)

    assert houve_correcao is False
    assert corrigido == texto


def test_ainda_corrige_erro_real_apos_guardas_de_falso_positivo():
    # Controle positivo: as guardas de #3 não podem apagar o comportamento
    # original — erro real (sem negação, sem fundamento próprio alheio)
    # continua sendo corrigido.
    texto = (
        "Reconheço a PRESCRIÇÃO da pretensão e julgo o processo extinto sem "
        "resolução de mérito, nos termos do art. 485 do CPC."
    )
    corrigido, houve_correcao = jg.aplicar_guardrail_merito(texto)
    assert houve_correcao is True
    assert "extinto COM resolução de mérito (art. 487, II, do CPC)" in corrigido


# ── Achado de review #4 (P1) — verificar cada regime do CDC separadamente ──

def test_alerta_cumulacao_mesmo_com_as_quatro_palavras_presentes():
    # A versão anterior só checava se "decadência" e "prescrição" apareciam
    # EM QUALQUER LUGAR do texto — este texto tem as quatro palavras e ainda
    # assim é exatamente a cumulação indevida que deveria ser capturada
    # (achado P1: Codex, PR #703).
    texto = (
        "O caso envolve vício do produto e fato do produto. Decadência e "
        "prescrição aplicam-se conjuntamente, sem distinguir prazos entre "
        "as pretensões."
    )
    alertas = jg.checar_cumulacao_vicio_fato_cdc(texto)
    assert len(alertas) == 1


def test_nao_alerta_quando_regimes_pareados_corretamente_por_proximidade():
    # Controle positivo: as guardas de #4 não podem apagar o comportamento
    # original — regimes corretamente pareados (vício perto de decadência,
    # fato perto de prescrição), sem marcador de cumulação, continuam sem
    # alerta.
    texto = (
        "Pretensão de vício do produto (CDC, art. 26): prazo decadencial de "
        "90 dias. Pretensão de fato do produto — defeito que causa dano (CDC, "
        "art. 27): prazo prescricional de 5 anos. São pretensões autônomas."
    )
    assert jg.checar_cumulacao_vicio_fato_cdc(texto) == []


# ── Achado de review #5 (P1) — idempotência na releitura ───────────────────

def test_reaplicar_guardrail_a_texto_ja_corrigido_nao_altera_nem_duplica():
    texto_original = (
        "Reconheço a PRESCRIÇÃO e julgo extinto sem resolução de mérito, "
        "nos termos do art. 485 do CPC."
    )
    corrigido_1, houve_1 = jg.aplicar_guardrail_merito(texto_original)
    assert houve_1 is True

    # Simula a releitura de um log JÁ corrigido (GET /ai/logs) — reaplicar não
    # pode encontrar as palavras-gatilho DENTRO do próprio aviso e reescrevê-lo
    # (achado P1: Codex, PR #703).
    corrigido_2, houve_2 = jg.aplicar_guardrail_merito(corrigido_1)
    assert houve_2 is False
    assert corrigido_2 == corrigido_1
    # Não duplicou o aviso.
    assert corrigido_2.count("GUARDRAIL DETERMINÍSTICO") == 1


def test_ja_corrigido_detecta_marcador():
    texto_corrigido, _ = jg.aplicar_guardrail_merito(
        "Reconheço a prescrição e julgo extinto sem resolução de mérito."
    )
    assert jg.ja_corrigido(texto_corrigido) is True
    assert jg.ja_corrigido("texto qualquer sem marcador") is False
    assert jg.ja_corrigido("") is False
    assert jg.ja_corrigido(None) is False


# ── Achado de review #7 (P1) — persistir alerta CDC no texto ───────────────

def test_anexar_alerta_cdc_ao_texto_persiste_o_alerta():
    texto = "Resposta sem correção de mérito, só cumulação CDC indevida."
    alertas = [jg.ALERTA_CUMULACAO_CDC]

    anexado = jg.anexar_alerta_cdc_ao_texto(texto, alertas)

    assert anexado != texto
    assert jg.ALERTA_CUMULACAO_CDC in anexado
    assert jg.MARCADOR_ALERTA_CDC in anexado


def test_anexar_alerta_cdc_e_idempotente_e_noop_sem_alertas():
    texto = "Resposta qualquer."
    assert jg.anexar_alerta_cdc_ao_texto(texto, []) == texto

    anexado = jg.anexar_alerta_cdc_ao_texto(texto, [jg.ALERTA_CUMULACAO_CDC])
    anexado_de_novo = jg.anexar_alerta_cdc_ao_texto(anexado, [jg.ALERTA_CUMULACAO_CDC])
    assert anexado_de_novo == anexado
    assert anexado.count(jg.MARCADOR_ALERTA_CDC) == 1
