# ── app/services/ia_parser.py ────────────────────────────────────────────────
# BUG-03: extração segura de título de caso a partir de respostas de IA.
#
# O modelo (Groq/Llama) às vezes responde com JSON — cru, cercado por ```json,
# ou embutido em texto conversacional. Persistir esse blob como `titulo` do caso
# poluiu o banco (ex.: DPT-2026-0013). Este módulo centraliza a extração:
#   1. remove cercas de código (```json … ```);
#   2. tenta json.loads e procura chaves de título conhecidas (inclui aninhado
#      identificacao_processual.assunto);
#   3. fallback por regex para JSON parcial/quebrado;
#   4. fallback texto plano (primeira linha, truncado em 200);
#   5. senão, rótulo de revisão manual.
from __future__ import annotations

import json
import re
from typing import Optional

FALLBACK = "Caso sem título (revisar manualmente)"

# Ordem de preferência das chaves de título no JSON da IA.
_CHAVES_TITULO = ("titulo", "title", "assunto", "nome", "descricao")

# Regex p/ remover cercas de código markdown (```json … ``` ou ``` … ```).
_FENCE_ABRE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?", re.MULTILINE)
_FENCE_FECHA = re.compile(r"\n?\s*```\s*$", re.MULTILINE)

# Regex fallback: captura "titulo"/"assunto"/etc "valor" mesmo em JSON quebrado.
_REGEX_TITULO = re.compile(
    r'"(?:titulo|title|assunto|nome|descricao)"\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)


def _remover_cercas(texto: str) -> str:
    """Remove cercas de código markdown ao redor do conteúdo."""
    t = _FENCE_ABRE.sub("", texto, count=1)
    t = _FENCE_FECHA.sub("", t)
    return t.strip()


def _extrair_bloco_json(texto: str) -> Optional[str]:
    """Isola o primeiro objeto/array JSON balanceado dentro de `texto`."""
    inicio = None
    for i, ch in enumerate(texto):
        if ch in "{[":
            inicio = i
            break
    if inicio is None:
        return None
    abre = texto[inicio]
    fecha = "}" if abre == "{" else "]"
    profundidade = 0
    for j in range(inicio, len(texto)):
        if texto[j] == abre:
            profundidade += 1
        elif texto[j] == fecha:
            profundidade -= 1
            if profundidade == 0:
                return texto[inicio:j + 1]
    return None


def _titulo_de_dict(data: dict) -> Optional[str]:
    """Procura uma chave de título no dict (nível raiz + identificacao_processual)."""
    # 1) chaves diretas, na ordem de preferência
    for chave in _CHAVES_TITULO:
        val = data.get(chave)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # 2) aninhado em identificacao_processual
    ident = data.get("identificacao_processual")
    if isinstance(ident, dict):
        for chave in _CHAVES_TITULO:
            val = ident.get(chave)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def sanitizar_resposta_ia(resposta: str) -> Optional[dict]:
    """Retorna o dict JSON da resposta da IA (removendo cercas), ou None.

    None quando: entrada vazia, não é JSON, ou o JSON não é um objeto (ex.: lista).
    """
    if not resposta or not isinstance(resposta, str):
        return None
    limpo = _remover_cercas(resposta)
    if not limpo:
        return None
    # tentativa direta
    try:
        obj = json.loads(limpo)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    # tentativa: isolar bloco JSON embutido em texto
    bloco = _extrair_bloco_json(limpo)
    if bloco:
        try:
            obj = json.loads(bloco)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def extrair_titulo_caso(resposta_ia: str) -> str:
    """Extrai um título de caso legível a partir de uma resposta de IA.

    Nunca lança; sempre retorna uma string (FALLBACK como último recurso).
    """
    if not resposta_ia or not isinstance(resposta_ia, str) or not resposta_ia.strip():
        return FALLBACK

    limpo = _remover_cercas(resposta_ia)
    if not limpo:
        return FALLBACK

    # 1) JSON válido (direto)
    try:
        obj = json.loads(limpo)
        if isinstance(obj, dict):
            titulo = _titulo_de_dict(obj)
            return titulo if titulo else FALLBACK
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) JSON embutido em texto (bloco balanceado)
    bloco = _extrair_bloco_json(limpo)
    if bloco:
        try:
            obj = json.loads(bloco)
            if isinstance(obj, dict):
                titulo = _titulo_de_dict(obj)
                if titulo:
                    return titulo
        except (json.JSONDecodeError, ValueError):
            pass

    # 3) Se parece JSON (começa com { ou [) mas não parseou → regex fallback
    if limpo.lstrip().startswith(("{", "[")):
        m = _REGEX_TITULO.search(limpo)
        if m:
            return m.group(1).strip()
        return FALLBACK

    # 4) Texto plano: primeira linha não vazia, truncada em 200
    for linha in limpo.splitlines():
        linha = linha.strip()
        if linha:
            return linha[:200]

    return FALLBACK


def titulo_e_json_bruto(titulo: str) -> bool:
    """Guard do endpoint: True se o título contém JSON/código cru.

    Objetos JSON e cercas Markdown continuam bloqueados. Para `[`, porém, o
    bloqueio só se aplica quando o primeiro bloco balanceado é um array JSON
    válido. Assim, rótulos humanos como `[URGENTE] Recurso` são aceitos.
    """
    if not titulo or not isinstance(titulo, str):
        return False
    t = titulo.lstrip()
    if t.startswith(("```", "{")):
        return True
    if not t.startswith("["):
        return False

    bloco = _extrair_bloco_json(t)
    if not bloco:
        return False
    try:
        return isinstance(json.loads(bloco), list)
    except (json.JSONDecodeError, ValueError):
        return False
