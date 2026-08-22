# ── app/services/ai/pseudonymizer.py ─────────────────────────────────────────
# Pseudonimização REVERSÍVEL e CONSISTENTE de PII (LGPD art. 33/46).
#
# Diferente de `sanitizer.py` (mascaramento IRREVERSÍVEL — [CPF], [PARTE_1]),
# aqui cada entidade recebe um marcador CONSISTENTE por TIPO+ÍNDICE
# ([CPF_1], [CLIENTE_1], [PROCESSO_1]…): a MESMA entidade vira o MESMO marcador
# em todo o texto e entidades distintas ganham índices distintos. Isso PRESERVA
# a RELAÇÃO entre os elementos ("[CLIENTE_1] processa [PARTE_CONTRARIA_1]"),
# permitindo que o provider externo raciocine sobre a estrutura do caso sem
# jamais ver o dado pessoal em claro. Um `mapa` (marcador → valor real) permite
# REIDRATAR a resposta localmente.
#
# ⚠️  SEGURANÇA / LGPD — o `mapa` CONTÉM PII REAL:
#   • NUNCA logar (logger/print), persistir em banco (AILog/Langfuse) nem enviar
#     a provider externo. Ele vive SÓ EM MEMÓRIA durante a request.
#   • O que sai para Anthropic/Groq é o texto PSEUDONIMIZADO (só marcadores).
#   • A reidratação acontece localmente, no VPS, sobre a resposta do modelo.
#
# Reutiliza os padrões regex de `sanitizer.py` (fonte única — não duplicar).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re
from collections import defaultdict

from app.services.sanitizer import (
    _APOS_CARTAO, _PATTERNS, _NASCIMENTO, mascarar_cartoes, validar_sem_pii,
)

# Placeholder do sanitizer → nome de TIPO usado no marcador pseudonimizado.
# (Ordem de aplicação = ordem de `_PATTERNS`, a MESMA do sanitizer, para não
#  haver sobreposição entre CPF/CNPJ/processo/telefone/CEP.)
_TIPO_POR_PLACEHOLDER = {
    "[CPF]": "CPF",
    "[CNPJ]": "CNPJ",
    "[PROCESSO]": "PROCESSO",
    "RG [RG]": "RG",
    "[EMAIL]": "EMAIL",
    "[TELEFONE]": "TELEFONE",
    "[CEP]": "CEP",
    "[CARTAO]": "CARTAO",
    "[CHAVE_PIX]": "CHAVE_PIX",
    "[OAB]": "OAB",
    "[ENDERECO]": "ENDERECO",
}

# Entidades nomeadas (nomes próprios) → tipo do marcador. As chaves são as
# esperadas no dict `entidades` de `pseudonimizar`.
_TIPO_POR_ENTIDADE = {
    "cliente": "CLIENTE",
    "empresa": "EMPRESA",
    "advogado": "ADVOGADO",
    "parte_contraria": "PARTE_CONTRARIA",
}

# Ordem determinística de processamento das entidades nomeadas.
_ORDEM_ENTIDADES = ("cliente", "empresa", "advogado", "parte_contraria")


class _Pseudonimizador:
    """Motor com ESTADO compartilhado: garante marcadores consistentes ao longo
    de várias chamadas (ex.: system + user de uma mesma request)."""

    def __init__(self) -> None:
        # valor real → marcador (consistência: mesma entidade, mesmo marcador)
        self._reverso: dict[str, str] = {}
        # marcador → valor real (mapa de reidratação; contém PII — nunca sai)
        self.mapa: dict[str, str] = {}
        self._contador: dict[str, int] = defaultdict(int)

    def _marcador(self, tipo: str, valor: str) -> str:
        """Retorna o marcador consistente para `valor` (cria um novo se inédito)."""
        if valor in self._reverso:
            return self._reverso[valor]
        self._contador[tipo] += 1
        marcador = f"[{tipo}_{self._contador[tipo]}]"
        self._reverso[valor] = marcador
        self.mapa[marcador] = valor
        return marcador

    def _substituir_entidades(self, texto: str, entidades: dict[str, list[str]] | None) -> str:
        if not entidades:
            return texto
        for chave in _ORDEM_ENTIDADES:
            tipo = _TIPO_POR_ENTIDADE[chave]
            for nome in entidades.get(chave, []) or []:
                nome = (nome or "").strip()
                if len(nome) < 4:  # mesmo piso do sanitizer (evita falso-positivo)
                    continue
                # Lookahead/lookbehind de não-palavra (cobre "S.A.", "Ltda.")
                padrao = rf"(?<!\w){re.escape(nome)}(?!\w)"
                if not re.search(padrao, texto, flags=re.IGNORECASE):
                    continue  # nome ausente: não polui o mapa com marcador órfão
                marcador = self._marcador(tipo, nome)
                texto = re.sub(padrao, marcador, texto, flags=re.IGNORECASE)
        return texto

    def _substituir_estruturais(self, texto: str) -> str:
        # Padrões estruturados (CPF, CNPJ, processo, e-mail, telefone, CEP…),
        # na MESMA ordem do sanitizer para evitar sobreposição.
        def _aplicar(entradas):
            nonlocal texto
            for pattern, placeholder in entradas:
                # .get com fallback "PII": placeholder novo no sanitizer não quebra
                # o gateway (degrada seguro; teste de sincronismo cobre a paridade).
                tipo = _TIPO_POR_PLACEHOLDER.get(placeholder, "PII")
                texto = pattern.sub(lambda m, _t=tipo: self._marcador(_t, m.group(0)), texto)

        # O cartão entra ENTRE os índices 4 e 5, pela mesma razão do sanitizer:
        # depois de CPF/CNPJ/processo e ANTES de TELEFONE, que num PAN agrupado
        # morde o miolo e deixa dígitos em claro. `mascarar_cartoes` conta os
        # dígitos (13–19) — regra que a entrada regex de `_PATTERNS` não cobre
        # sozinha; sem esta linha o gateway pseudonimizado ficaria com a
        # cobertura antiga, estreita.
        _aplicar(_PATTERNS[:5])
        texto = mascarar_cartoes(
            texto, lambda m: self._marcador("CARTAO", m.group(0)))
        _aplicar(_APOS_CARTAO)
        # Datas de nascimento contextuais → marcador único (mantém round-trip).
        texto = _NASCIMENTO.sub(lambda m: self._marcador("DATA_NASC", m.group(0)), texto)
        return texto

    def _substituir_nomes_livres(self, texto: str) -> str:
        """3ª passada — NER LOCAL (issue #102): pseudonimiza NOMES DE PESSOA
        residuais em texto livre/OCR/RAG que NÃO estavam em `entidades` (vítima,
        testemunha, terceiro citados só no documento). Roda por ÚLTIMO: os
        marcadores já criados ([CLIENTE_1], [CPF_1]…) são ALL-CAPS entre colchetes
        e nunca são reconhecidos como nome (não há dupla marcação). Cada nome vira
        [PESSOA_n] consistente/reversível; substitui do mais LONGO ao mais curto."""
        from app.services.ai.ner_local import detectar_empresas, detectar_nomes
        # P0-474: EMPRESAS primeiro (razão social é mais longa e contém tokens
        # que também casariam como "nome de pessoa"; substituir antes evita
        # marcação parcial tipo "Transportadora [PESSOA_1] Ltda").
        for razao in detectar_empresas(texto):
            padrao = rf"(?<!\w){re.escape(razao)}(?!\w)"
            if not re.search(padrao, texto):
                continue
            marcador = self._marcador("EMPRESA", razao)
            texto = re.sub(padrao, marcador, texto)
        for nome in detectar_nomes(texto, incluir_medio=True):
            padrao = rf"(?<!\w){re.escape(nome)}(?!\w)"
            if not re.search(padrao, texto):
                continue
            marcador = self._marcador("PESSOA", nome)
            texto = re.sub(padrao, marcador, texto)
        return texto

    def processar(self, texto: str, entidades: dict[str, list[str]] | None = None) -> str:
        texto = self._substituir_entidades(texto, entidades)
        texto = self._substituir_estruturais(texto)
        texto = self._substituir_nomes_livres(texto)
        return texto


def pseudonimizar(
    texto: str,
    entidades: dict[str, list[str]] | None = None,
) -> tuple[str, dict[str, str]]:
    """Pseudonimiza `texto` de forma REVERSÍVEL e CONSISTENTE.

    Args:
      texto:     texto livre (prompt) que irá a um provider externo.
      entidades: nomes próprios a proteger por tipo, ex.:
                 {"cliente": ["João da Silva"], "empresa": ["ACME Ltda"],
                  "advogado": [...], "parte_contraria": [...]}.

    Returns:
      (texto_pseudonimizado, mapa) — `mapa` = {marcador: valor_real}.
      ⚠️ `mapa` contém PII real: nunca logar/persistir/enviar a externo.
    """
    motor = _Pseudonimizador()
    novo = motor.processar(texto or "", entidades)
    return novo, motor.mapa


def pseudonimizar_mensagens(
    messages: list[dict],
    entidades: dict[str, list[str]] | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """Pseudonimiza uma LISTA de mensagens (formato OpenAI) com ESTADO
    COMPARTILHADO: a mesma entidade recebe o mesmo marcador em todas as
    mensagens (system + user), preservando a relação entre elas.

    Returns:
      (mensagens_pseudonimizadas, mapa). ⚠️ `mapa` contém PII: nunca sai do VPS.
    """
    motor = _Pseudonimizador()
    limpos: list[dict] = []
    for m in messages:
        novo = dict(m)
        novo["content"] = motor.processar(m.get("content", "") or "", entidades)
        limpos.append(novo)
    return limpos, motor.mapa


def reidratar(texto: str, mapa: dict[str, str]) -> str:
    """Reidrata `texto` substituindo cada marcador do `mapa` pelo valor real.

    - Só substitui o marcador EXATO (string literal). Idempotente: rodar duas
      vezes não altera o resultado (após a 1ª, os marcadores já não existem).
    - Marcador ausente no texto é ignorado (sem erro).
    - Substitui do marcador mais LONGO para o mais curto por segurança extra
      (os delimitadores `[`/`]` já evitam colisão de prefixo, ex.: [X_1] vs [X_10]).
    """
    if not texto or not mapa:
        return texto or ""
    for marcador in sorted(mapa, key=len, reverse=True):
        texto = texto.replace(marcador, mapa[marcador])
    return texto


def validar_sem_pii_pseudonimizado(texto: str) -> list[str]:
    """Segunda barreira: reusa `validar_sem_pii` do sanitizer para garantir que
    o texto pseudonimizado não deixou PII estrutural residual em claro.
    Retorna a lista de tipos residuais (vazia = limpo).

    REDE DE SEGURANÇA (issue #102): além da PII estrutural, sinaliza 'PESSOA'
    quando sobrar um NOME de ALTA confiança (gatilho de contexto — "vítima X",
    "testemunha Y") EM CLARO após a pseudonimização. No fluxo normal o motor já
    substituiu esses nomes por [PESSOA_n], então isto fica vazio; só dispara se
    um nome escapou — aí o gateway PULA o provider externo (defense-in-depth,
    sobretudo em sigilo). NÃO usa a heurística MÉDIA (capitalização) para não
    super-bloquear termos institucionais/jurídicos capitalizados."""
    from app.services.ai.ner_local import contem_nome_alta_confianca
    residual = validar_sem_pii(texto)
    if contem_nome_alta_confianca(texto):
        residual = residual + ["PESSOA"]
    return residual
