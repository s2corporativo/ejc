"""
veredito_ia.py — Veredito IA: análise de probabilidade de êxito de uma tese.

REESCRITO na auditoria de 04/07/2026. A versão anterior era FAKE com tela ativa:
probabilidade por heurística fixa (base 0.5 + bônus por palavra-chave) e
jurisprudência hardcoded ("Jurisprudência relevante 1", http://link1.com) —
inaceitável num sistema jurídico. Agora usa SOMENTE motores reais do EJC:

  1. PROBABILIDADE — jurimetria interna (app/services/jurimetria.py) sobre os
     casos ENCERRADOS reais da área. Amostra < MIN_AMOSTRA → probabilidade None
     com explicação honesta (padrão OAB já adotado no motor estratégico:
     estatística inventada viola a OAB).
  2. JURISPRUDÊNCIA — RAG interno (pgvector, buscar_contexto_rag) nas categorias
     públicas de jurisprudência/súmulas, com escopo de cliente quando há case_id.
     Sem resultados → lista VAZIA + aviso. Nada é inventado.
  3. ANÁLISE QUALITATIVA — AI Gateway central (task_type="jurimetria"), com a
     base anti-alucinação padrão do escritório. Toda saída é RASCUNHO (HITL).
  4. VERIFICAÇÃO — citation_check.verificar_citacoes sobre o material retornado;
     score e avisos anexados à resposta.
  5. AUDITORIA — AILog via registrar_ai_log (LGPD/OAB); erro de log propaga.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import List, Optional

from app.core.victory_vault import VictoryVault
from app.models.ai_log import AITipoUso
from app.schemas.veredito_ia_schema import (
    AnaliseTeseResponse, TeseVitoriosaSimilar,
    JurisprudenciaSuporte, SugestaoContextualizada,
)
from app.services.ai_guard import sanitizar_ou_abortar, registrar_ai_log
from app.services.sanitizer import sanitizar_pii
from app.services.ai_service import buscar_contexto_rag, _escopo_cliente_do_caso
from app.services.citation_check import verificar_citacoes
from app.services.jurimetria import jurimetria as calcular_jurimetria, MIN_AMOSTRA

logger = logging.getLogger("ejc.veredito_ia")

AVISO_HITL = ("Rascunho gerado por IA e estatística interna — NÃO é parecer. "
              "Revisão humana por advogado é obrigatória antes de qualquer uso (HITL/OAB).")

# Honestidade epistêmica: `probabilidade_exito` NÃO é predição de LLM — é taxa
# estatística determinística (jurimetria sobre casos ENCERRADOS reais).
# Ver `metodo_probabilidade` no schema de resposta.
_METODO_PROBABILIDADE = "estatistica_historica_deterministica"
AVISO_METODO_PROBABILIDADE = (
    "A probabilidade de êxito NÃO é uma predição de IA/LLM: é uma taxa "
    "estatística determinística calculada sobre os casos ENCERRADOS reais do "
    "escritório (jurimetria interna). Apenas as sugestões contextualizadas "
    "abaixo são geradas por IA (rascunho sujeito a revisão — HITL/OAB)."
)

# Categorias PÚBLICAS de jurisprudência no RAG (mesmo conjunto do motor de teses).
_CATS_JURISPRUDENCIA = ["jurisprudencia", "sumula_stf", "sumula_stj", "sumula_tst"]

# Frontend usa rótulos com acento/variação ("Civel", "Penal", "Tributaria");
# Case.area usa o enum CaseArea. Sinônimos após normalização (sem acento, lower).
_AREA_SINONIMOS = {
    "civel": "civil",
    "penal": "criminal",
    "tributaria": "tributario",
    "previdenciaria": "previdenciario",
}

_RE_TRIBUNAL = re.compile(
    r"\b(STF|STJ|TST|TSE|STM|TRF-?\d|TRT-?\d{1,2}|TJ[A-Z]{2})\b", re.I)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip().lower()


def _grupo_da_area(grupos: list[dict], area_juridica: str) -> Optional[dict]:
    alvo = _norm(area_juridica)
    alvo = _AREA_SINONIMOS.get(alvo, alvo)
    for g in grupos:
        if _norm(str(g.get("grupo", ""))) == alvo:
            return g
    return None


def _tribunal_de(chunk: dict) -> str:
    texto = f"{chunk.get('titulo') or ''} {chunk.get('fonte') or ''}"
    m = _RE_TRIBUNAL.search(texto)
    return m.group(1).upper() if m else "Base interna"


def _link_de(chunk: dict) -> Optional[str]:
    fonte = (chunk.get("fonte") or "").strip()
    return fonte if fonte.startswith(("http://", "https://")) else None


def _parse_sugestoes(texto: str) -> Optional[List[SugestaoContextualizada]]:
    """Extrai {"sugestoes":[{tipo,descricao}]} do texto da IA (tolerante a prosa)."""
    try:
        ini, fim = texto.find("{"), texto.rfind("}")
        if ini < 0 or fim <= ini:
            return None
        data = json.loads(texto[ini:fim + 1])
        out: List[SugestaoContextualizada] = []
        for s in data.get("sugestoes", []):
            desc = str(s.get("descricao") or "").strip()
            if desc:
                out.append(SugestaoContextualizada(
                    tipo=str(s.get("tipo") or "Sugestão")[:60], descricao=desc))
        return out or None
    except Exception:
        return None


class VereditoIA:
    def __init__(self):
        self.victory_vault = VictoryVault()

    async def predict_success(
        self,
        tese_juridica: str,
        area_juridica: str,
        tribunais_selecionados: List[str],
        *,
        db,
        user,
        case_id: Optional[str] = None,
    ) -> AnaliseTeseResponse:
        avisos: List[str] = [AVISO_HITL, AVISO_METODO_PROBABILIDADE]

        # LGPD: sanitiza a tese ANTES de qualquer uso (aborta 422 se sobrar PII
        # estrutural — a mesma guarda dos demais endpoints de IA).
        tese_limpa, pii_removida = sanitizar_ou_abortar(tese_juridica)
        # Auditoria P2: area/tribunais são texto LIVRE do usuário e também vão
        # ao gateway externo e ao AILog — passam pelo mesmo guard. (Para o
        # matching interno de jurimetria usamos o valor original.)
        area_limpa, _ = sanitizar_pii(area_juridica or "")
        tribunais_limpos = [sanitizar_pii(t or "")[0] for t in (tribunais_selecionados or [])]

        # ── 1. Probabilidade: jurimetria REAL (casos encerrados da área) ─────
        probabilidade: Optional[float] = None
        fonte_prob: Optional[str] = None
        n_amostra = 0
        try:
            dados = await calcular_jurimetria(db, user, dimensao="area")
            grupo = _grupo_da_area(dados.get("grupos", []), area_juridica)
            n_amostra = int(grupo["n"]) if grupo else 0
            if grupo and grupo.get("amostra_suficiente") and \
                    grupo.get("taxa_exito_com_acordo") is not None:
                probabilidade = round(grupo["taxa_exito_com_acordo"] / 100.0, 3)
                fonte_prob = (
                    f"Jurimetria interna: taxa histórica real de desfecho favorável "
                    f"(êxito total + parcial + acordo) em {grupo['n']} caso(s) "
                    f"encerrado(s) da área '{grupo['grupo']}'."
                )
            else:
                avisos.append(
                    f"Amostra histórica insuficiente na área '{area_juridica}' "
                    f"(n={n_amostra} < {MIN_AMOSTRA} casos encerrados): probabilidade "
                    "NÃO informada — estatística inventada viola o padrão OAB do escritório."
                )
        except Exception as e:
            logger.warning(f"Veredito IA: jurimetria indisponível: {e}")
            avisos.append("Jurimetria interna indisponível no momento — "
                          "probabilidade não calculada.")

        # ── 2. Teses vitoriosas reais do Victory Vault (Postgres) ────────────
        teses_similares: List[TeseVitoriosaSimilar] = []
        try:
            teses_raw = await self.victory_vault.get_teses_vitoriosas(
                area_juridica=area_juridica)
            teses_similares = [
                TeseVitoriosaSimilar(
                    id=str(t.id), titulo=t.titulo, ementa=t.ementa,
                    area_juridica=t.area_juridica, data_vitoria=t.data_vitoria,
                    link=t.link,
                ) for t in teses_raw[:5]
            ]
        except Exception as e:
            logger.warning(f"Veredito IA: Victory Vault indisponível: {e}")

        # ── 3. Jurisprudência REAL: RAG interno (escopo do cliente do caso) ──
        jurisprudencia: List[JurisprudenciaSuporte] = []
        chunks: list[dict] = []
        try:
            escopo_cli = await _escopo_cliente_do_caso(db, case_id)
            consulta = f"{area_juridica} {tese_limpa}"[:400]
            chunks = await buscar_contexto_rag(
                db, consulta, limite=5, categorias=_CATS_JURISPRUDENCIA,
                modo_or=True, scope_client_id=escopo_cli)
            jurisprudencia = [
                JurisprudenciaSuporte(
                    id=str(c.get("chunk_id") or i),
                    ementa=(c.get("conteudo") or "").strip()[:500],
                    tribunal=_tribunal_de(c),
                    data=str(c.get("data") or ""),
                    link=_link_de(c),
                ) for i, c in enumerate(chunks)
            ]
        except Exception as e:
            logger.warning(f"Veredito IA: busca RAG falhou: {e}")
        if not jurisprudencia:
            avisos.append(
                "Nenhuma jurisprudência localizada na base interna (RAG) para esta "
                "tese — a lista vem vazia porque nada é inventado. Considere ingerir "
                "fontes oficiais na base de conhecimento.")

        # ── 4. Análise qualitativa via AI Gateway (anti-alucinação, HITL) ────
        texto_ia = ""
        sugestoes: List[SugestaoContextualizada] = []
        contexto = "\n".join(
            f"- {(c.get('titulo') or 'sem título')}: {(c.get('conteudo') or '')[:200]}"
            for c in chunks) or "(nenhuma jurisprudência interna encontrada)"
        historico = "\n".join(
            f"- {t.titulo}: {t.ementa[:160]}" for t in teses_similares) or "(sem histórico)"
        system_msg = (
            "Você é consultor jurídico estratégico. Avalie a tese APENAS com base no "
            "contexto fornecido (jurisprudência interna e histórico de vitórias do "
            "escritório). É PROIBIDO inventar julgado, súmula, artigo ou estatística "
            "que não esteja no contexto — se faltar base, diga 'requer pesquisa'. "
            "NUNCA prometa resultado nem estime percentuais. Toda saída é RASCUNHO "
            "com revisão obrigatória do advogado (OAB)."
        )
        user_msg = (
            f"ÁREA: {area_limpa} | TRIBUNAIS DE INTERESSE: "
            f"{', '.join(tribunais_limpos) or '(não informados)'}\n\n"
            f"TESE:\n{tese_limpa[:2000]}\n\n"
            f"JURISPRUDÊNCIA INTERNA RECUPERADA:\n{contexto}\n\n"
            f"TESES VITORIOSAS DO ESCRITÓRIO NA ÁREA:\n{historico}\n\n"
            'Responda APENAS JSON: {"sugestoes": [{"tipo": "Melhoria|Risco|Pesquisa|Estrategia", '
            '"descricao": "sugestão objetiva ancorada no contexto"}]}'
        )
        resp = None
        try:
            # Import em runtime (padrão do motor de teses/análise estratégica):
            # permite monkeypatch de app.services.ai_gateway.chat nos testes.
            from app.services.ai_gateway import chat as gw_chat
            # Nomes próprios do caso → marcadores reversíveis antes do provider
            # externo (jurimetria = EXTERNO_PSEUDONIMIZADO). Só há contexto de
            # caso quando case_id foi informado; sem ele, PII estrutural apenas.
            entidades = None
            if case_id:
                from app.services.ai.entidades_caso import entidades_do_caso
                entidades = await entidades_do_caso(db, case_id)
            resp = await gw_chat(
                messages=[{"role": "system", "content": system_msg},
                          {"role": "user", "content": user_msg}],
                task_type="jurimetria", temperature=0.2, max_tokens=1200,
                entidades=entidades or None)
        except Exception as e:
            logger.warning(f"Veredito IA: gateway indisponível: {e}")
            avisos.append("Análise qualitativa de IA indisponível no momento — "
                          "sugestões não geradas.")
        if resp is not None:
            # AILog OBRIGATÓRIO: erro de gravação propaga (IA sem rastro não sai).
            await registrar_ai_log(
                db,
                user_id=str(user.id),
                tipo_uso=AITipoUso.analise_caso,
                case_id=case_id,
                prompt_sanitizado=user_msg,
                pii_removida=pii_removida,
                resposta=resp.texto,
                modelo=f"{resp.provedor}/{resp.modelo}",
                fontes_rag=json.dumps(
                    [c.get("titulo") for c in chunks], ensure_ascii=False) or None,
                tokens_input=getattr(resp, "input_tokens", None),
                tokens_output=getattr(resp, "output_tokens", None),
            )
            texto_ia = resp.texto or ""
            sugestoes = _parse_sugestoes(texto_ia) or [SugestaoContextualizada(
                tipo="Análise IA (rascunho)", descricao=texto_ia.strip()[:800])]

        # ── 5. Verificador anti-alucinação sobre o material retornado ────────
        score_citacoes: Optional[int] = None
        material = "\n".join([texto_ia] + [j.ementa for j in jurisprudencia]).strip()
        if material:
            try:
                relatorio = await verificar_citacoes(db, material)
                score_citacoes = relatorio.get("score")
                for a in (relatorio.get("avisos") or []):
                    if a not in avisos:
                        avisos.append(a)
            except Exception as e:
                logger.warning(f"Veredito IA: verificador de citações falhou: {e}")
                avisos.append("Verificador de citações indisponível — confirme "
                              "manualmente cada citação antes de usar.")

        return AnaliseTeseResponse(
            probabilidade_exito=probabilidade,
            fonte_probabilidade=fonte_prob,
            metodo_probabilidade=_METODO_PROBABILIDADE,
            n_amostra=n_amostra,
            teses_vitoriosas_similares=teses_similares,
            jurisprudencia_suporte=jurisprudencia,
            sugestoes_contextualizadas=sugestoes,
            score_citacoes=score_citacoes,
            avisos=avisos,
            status_hitl="rascunho",
        )
