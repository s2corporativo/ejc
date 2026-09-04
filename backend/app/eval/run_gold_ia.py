# ── app/eval/run_gold_ia.py ──────────────────────────────────────────────────
# RÉGUA DAS CINCO CAPACIDADES DE IA (item I7 da análise E2E de 03/09/2026).
#
# "Mais inteligente" só deixa de ser opinião quando vira número comparável entre
# duas execuções. Este runner aplica o gold set de capacidades
# (`gold_set_ia_candidatos.jsonl`) contra a IA e pontua cada caso por:
#
#   • cobertura dos CRITÉRIOS (os pontos que a resposta tinha de enfrentar);
#   • cobertura das CITAÇÕES ESPERADAS POR TIPO (o gold set descreve o TIPO de
#     fonte — "artigo do CDC sobre vício do produto" — e nunca fixa número de
#     súmula/artigo que não tenha sido conferido em fonte oficial);
#   • conteúdo PROIBIDO (promessa de resultado, dispensa de revisão humana):
#     presença zera o caso, não desconta pontinho.
#
# Dois modos:
#   --mock  provedor FALSO determinístico (hash do id do caso). Roda em CI, sem
#           rede, banco ou chave de provedor. Mede o HARNESS, não a IA — e o
#           relatório diz isso em `mede_qualidade_juridica: false`.
#   (real)  chama a PORTA CANÔNICA da capacidade (`services/ai/core/capacidades`
#           → orquestrador único), sob um usuário real do banco, e com --juiz
#           adiciona o LLM-juiz (capacidade `analisar` como avaliador) e o
#           `citation_check`. Medir por atalho ao gateway media um pipeline sem
#           contexto, sem gate de citações e sem HITL — não o que se usa.
#
# GOVERNANÇA: todo caso do arquivo é `status: "candidato"` — proposta SEM
# atestação humana. Candidato nunca é apresentado como gold atestado, aqui nem
# em `gold_governance.py`. Enquanto `atestado_por` for null, o número serve para
# comparar execuções entre si, não para certificar a IA.
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
GOLD_PADRAO = os.path.join(BASE, "gold_set_ia_candidatos.jsonl")
RELATORIO_PADRAO = os.path.join(BASE, "relatorio_gold_ia.json")

# O modo real chama a PORTA CANÔNICA de cada capacidade
# (`services/ai/core/capacidades.py` → orquestrador único). Medir por um atalho
# ao gateway media um pipeline que nenhum usuário exercita: sem contexto do
# caso, sem gate de citações, sem carimbo HITL e sem RBAC — exatamente as
# camadas que decidem se a resposta presta.

_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e",
    "em", "entre", "na", "nao", "nas", "no", "nos", "o", "os", "ou", "para",
    "pela", "pelo", "por", "que", "se", "sem", "ser", "seu", "sua", "sobre",
    "um", "uma", "the", "of",
}
# Fração das palavras significativas do critério que precisa aparecer na
# resposta para considerá-lo enfrentado. 0.6 é deliberadamente tolerante:
# a régua mede se o ponto foi ENDEREÇADO, não se foi copiado.
LIMIAR_COBERTURA = 0.6


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(t.lower().replace("\n", " ").split())


def _palavras(frase: str) -> list[str]:
    return [p.strip(".,;:()[]'\"") for p in _norm(frase).split()
            if len(p) > 3 and p not in _STOPWORDS]


def _item_coberto(item: str, resposta_norm: str) -> bool:
    palavras = _palavras(item)
    if not palavras:
        return False
    presentes = sum(1 for p in palavras if p in resposta_norm)
    return (presentes / len(palavras)) >= LIMIAR_COBERTURA


# Marcadores de FONTE. Sem eles, "responsabilidade solidária dos fornecedores"
# contaria como citação do CDC só porque a resposta repetiu a tese — a régua
# passaria a medir vocabulário, não fundamentação. Exigir a fonte é o que
# separa "afirmou a tese" de "apontou onde ela está escrita".
_MARCADORES_FONTE = (
    "cdc", "codigo de defesa do consumidor", "clt", "codigo civil",
    "codigo penal", "codigo de processo", "codigo de transito", "constitucional",
    "constituicao", "sumul", "estatuto da crianca", "eca", "aviacao civil",
    "agencia reguladora", "lei ",
)


def _marcadores_de(tipo: str) -> list[str]:
    t = _norm(tipo)
    return [m for m in _MARCADORES_FONTE if m in t]


def _citacao_coberta(tipo: str, resposta_norm: str) -> bool:
    """Citação por TIPO: exige o assunto E o marcador da fonte na resposta."""
    if not _item_coberto(tipo, resposta_norm):
        return False
    marcadores = _marcadores_de(tipo)
    return any(m in resposta_norm for m in marcadores) if marcadores else True


def _cobertura(itens: list[str], resposta_norm: str, *,
               citacao: bool = False) -> tuple[float, list[str]]:
    """Fração coberta + lista do que FICOU DE FORA (o que interessa ao curador)."""
    if not itens:
        return 1.0, []
    coberto = _citacao_coberta if citacao else _item_coberto
    faltantes = [i for i in itens if not coberto(i, resposta_norm)]
    return round((len(itens) - len(faltantes)) / len(itens), 3), faltantes


def _proibidos_encontrados(caso: dict, resposta_norm: str) -> list[str]:
    return [p for p in (caso.get("nao_deve_conter") or []) if _norm(p) in resposta_norm]


def pontuar(caso: dict, resposta: str) -> dict:
    """Pontua UM caso. Score 0..1; conteúdo proibido zera (não desconta)."""
    rn = _norm(resposta)
    cob_crit, faltam_crit = _cobertura(list(caso.get("criterios") or []), rn)
    tipos = list(caso.get("citacoes_esperadas_tipo") or [])
    cob_cit, faltam_cit = _cobertura(tipos, rn, citacao=True)
    proibidos = _proibidos_encontrados(caso, rn)

    # Sem citação esperada (extrair/resumir), o peso vai todo para os critérios.
    score = round(cob_crit * 0.6 + cob_cit * 0.4, 3) if tipos else round(cob_crit, 3)
    if proibidos:
        score = 0.0
    return {
        "id": caso.get("id"),
        "capacidade": caso.get("capacidade"),
        "area": caso.get("area"),
        "cenario": caso.get("cenario"),
        "status": caso.get("status"),
        "score": score,
        "cobertura_criterios": cob_crit,
        "cobertura_citacoes_tipo": cob_cit,
        "criterios_nao_enfrentados": faltam_crit,
        "citacoes_tipo_ausentes": faltam_cit,
        "conteudo_proibido": proibidos,
        "aprovado": bool(not proibidos and cob_crit >= LIMIAR_COBERTURA
                         and (not tipos or cob_cit >= 0.5)),
        "chars_resposta": len(resposta or ""),
    }


# ── Provedor FALSO determinístico (modo --mock) ──────────────────────────────

def resposta_mock(caso: dict) -> str:
    """Resposta reprodutível derivada do id do caso.

    Não é "a IA respondendo bem": é um gerador estável que cobre parte dos
    critérios e, em alguns casos, dispara o caminho de conteúdo proibido — para
    que o CI exercite pontuação alta, pontuação baixa e reprovação por promessa
    de resultado sem depender de rede.
    """
    h = hashlib.sha256(str(caso.get("id") or "").encode("utf-8")).digest()
    linhas = [
        "[MOCK] Provedor falso determinístico — este texto NÃO mede qualidade "
        "jurídica; serve para exercitar a régua sem rede.",
    ]
    for i, criterio in enumerate(caso.get("criterios") or []):
        if h[i % len(h)] % 4 != 0:
            linhas.append(f"- {criterio}")
    for i, tipo in enumerate(caso.get("citacoes_esperadas_tipo") or []):
        if h[(i + 7) % len(h)] % 3 != 0:
            linhas.append(f"- fundamento indicado: {tipo}")
    proibidos = caso.get("nao_deve_conter") or []
    if proibidos and h[0] % 5 == 0:
        linhas.append(f"Observação indevida: {proibidos[0]}.")
    linhas.append("Rascunho sujeito à revisão humana (HITL obrigatório — OAB).")
    return "\n".join(linhas)


# ── Modo real: gateway + (opcional) juiz e gate de citações ──────────────────

async def _resolver_usuario(db, email: str | None):
    """Usuário sob o qual a régua roda. O orquestrador exige um usuário REAL:
    é ele que define RBAC, escopo de dados e o `user_id` do AILog."""
    from sqlalchemy import select

    from app.models.user import User, UserRole

    q = select(User).where(User.is_active.is_(True))
    if email:
        q = q.where(User.email == email)
    else:
        # Determinístico: o papel mais alto da equipe jurídica, desempatado por
        # e-mail. Sem isso, duas execuções da régua podem medir permissões
        # diferentes e o número deixa de ser comparável.
        q = q.where(User.role.in_([UserRole.superadmin, UserRole.socio, UserRole.advogado]))
    q = q.order_by(User.role.asc(), User.email.asc())
    user = (await db.execute(q)).scalars().first()
    if user is None:
        raise SystemExit(
            "Modo real exige um usuário ativo da equipe jurídica no banco "
            "(superadmin/sócio/advogado). Use --usuario <email> para escolher."
        )
    return user


async def _resposta_real(db, user, caso: dict, nivel: str | None) -> dict:
    """Executa o caso pela porta canônica da capacidade e devolve o envelope.

    `nivel` segue como veio: `None` significa "quem decide é o PISO por tarefa"
    — forçar "alto" aqui media um roteamento que a aplicação não usa e inflava
    o custo da régua.
    """
    from app.services.ai.core import capacidades

    capacidade = str(caso.get("capacidade") or "")
    if capacidade not in capacidades.CAPACIDADES:
        raise ValueError(f"capacidade desconhecida no gold set: {capacidade!r}")
    porta = getattr(capacidades, capacidade)
    opcoes: dict = {}
    if nivel:
        opcoes["nivel_inteligencia"] = nivel
    return await porta(db, user, mensagem=str(caso.get("entrada") or ""),
                       area=(caso.get("area") or None), opcoes=opcoes or None)


async def _juiz_llm(caso: dict, resposta: str) -> float | None:
    """LLM-juiz pela capacidade `analisar`: 0..1 de aderência aos critérios."""
    try:
        from app.services import ai_gateway

        criterios = "\n".join(f"- {c}" for c in (caso.get("criterios") or []))
        r = await ai_gateway.chat(
            [{"role": "system", "content": (
                "Voce e um avaliador juridico rigoroso. Dados CRITERIOS e RESPOSTA, "
                "responda APENAS um numero entre 0 e 1 (2 casas) = fracao dos "
                "criterios efetivamente enfrentados pela RESPOSTA. Nao explique.")},
             {"role": "user", "content": (
                 f"CRITERIOS:\n{criterios}\n\nRESPOSTA:\n{resposta[:6000]}\n\nNota (0..1):")}],
            task_type="analise_juridica", temperature=0.0, max_tokens=8,
            nivel_inteligencia="padrao",
        )
        import re
        m = re.search(r"[01](?:\.\d+)?", r.texto or "")
        return round(min(1.0, max(0.0, float(m.group(0)))), 3) if m else None
    except Exception as e:  # juiz é complemento, nunca requisito
        print(f"[juiz] indisponível: {e}", file=sys.stderr)
        return None


async def _citacoes_reais(db, resposta: str) -> dict | None:
    try:
        from app.services.citation_check import verificar_citacoes
        r = await verificar_citacoes(db, resposta or "")
        if isinstance(r, dict):
            return {"total": int(r.get("total") or 0),
                    "nao_confirmadas": int(r.get("nao_encontradas") or 0)}
    except Exception as e:
        print(f"[citation_check] indisponível: {e}", file=sys.stderr)
    return None


# ── Carga e agregação ────────────────────────────────────────────────────────

def carregar_gold(caminho: str) -> list[dict]:
    casos: list[dict] = []
    with open(caminho, encoding="utf-8") as fh:
        for n, linha in enumerate(fh, 1):
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            try:
                casos.append(json.loads(linha))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{os.path.basename(caminho)}:{n}: JSON inválido: {exc}")
    return casos


def _media(valores: list[float]) -> float:
    return round(sum(valores) / len(valores), 3) if valores else 0.0


def agregar(resultados: list[dict]) -> dict:
    def bloco(itens: list[dict]) -> dict:
        return {
            "n": len(itens),
            "score_medio": _media([i["score"] for i in itens]),
            "cobertura_criterios": _media([i["cobertura_criterios"] for i in itens]),
            "cobertura_citacoes_tipo": _media([i["cobertura_citacoes_tipo"] for i in itens]),
            "aprovados": sum(1 for i in itens if i["aprovado"]),
            "casos_com_conteudo_proibido": sum(1 for i in itens if i["conteudo_proibido"]),
        }

    por_area: dict[str, dict] = {}
    por_capacidade: dict[str, dict] = {}
    for chave, destino in (("area", por_area), ("capacidade", por_capacidade)):
        for valor in sorted({str(r.get(chave) or "") for r in resultados}):
            destino[valor] = bloco([r for r in resultados if str(r.get(chave) or "") == valor])
    return {"global": bloco(resultados), "por_area": por_area,
            "por_capacidade": por_capacidade}


def _governanca(casos: list[dict]) -> dict:
    candidatos = [c for c in casos if str(c.get("status") or "") == "candidato"]
    atestados = [c for c in casos if c.get("atestado_por")]
    return {
        "casos": len(casos),
        "candidatos_nao_atestados": len(candidatos),
        "atestados_por_humano": len(atestados),
        "aviso": (
            "Casos CANDIDATOS não são gold set atestado: sem curador, fonte "
            "oficial conferida e vigência, o número compara execuções entre si "
            "e não certifica a qualidade jurídica da IA."
        ) if candidatos else "",
    }


async def executar(
    casos: list[dict], *, mock: bool, juiz: bool, nivel: str | None,
    usuario: str | None = None,
) -> list[dict]:
    resultados: list[dict] = []
    db = None
    ctx = None
    user = None
    if not mock:
        from app.core.database import AsyncSessionLocal
        ctx = AsyncSessionLocal()
        db = await ctx.__aenter__()
        user = await _resolver_usuario(db, usuario)
        print(f"modo real: executando como {user.email} "
              f"({getattr(user.role, 'value', user.role)})", file=sys.stderr)
    try:
        for caso in casos:
            try:
                if mock:
                    resposta = resposta_mock(caso)
                    envelope = None
                else:
                    envelope = await _resposta_real(db, user, caso, nivel)
                    resposta = str(envelope.get("conteudo") or "")
                ponto = pontuar(caso, resposta)
                if not mock:
                    # O envelope canônico já traz o resultado do gate de
                    # citações e o carimbo HITL: é o que o usuário vê, e por
                    # isso entra no relatório.
                    ponto["status_hitl"] = envelope.get("status_hitl")
                    ponto["alertas"] = list(envelope.get("alertas") or [])
                    ponto["citacoes_declaradas"] = len(envelope.get("citacoes") or [])
                    ponto["fontes_declaradas"] = len(envelope.get("fontes_rag") or [])
                    if juiz:
                        ponto["juiz_llm"] = await _juiz_llm(caso, resposta)
                    citacoes = await _citacoes_reais(db, resposta)
                    if citacoes:
                        ponto["citacoes_verificadas"] = citacoes
            except Exception as e:  # um caso quebrado não derruba a régua
                ponto = {
                    "id": caso.get("id"), "capacidade": caso.get("capacidade"),
                    "area": caso.get("area"), "cenario": caso.get("cenario"),
                    "status": caso.get("status"), "score": 0.0,
                    "cobertura_criterios": 0.0, "cobertura_citacoes_tipo": 0.0,
                    "criterios_nao_enfrentados": [], "citacoes_tipo_ausentes": [],
                    "conteudo_proibido": [], "aprovado": False, "chars_resposta": 0,
                    "erro": str(e)[:300],
                }
            resultados.append(ponto)
    finally:
        if ctx is not None:
            await ctx.__aexit__(None, None, None)
    return resultados


def montar_relatorio(casos: list[dict], resultados: list[dict], *, mock: bool,
                     gold: str) -> dict:
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gold": os.path.basename(gold),
        "modo": "mock" if mock else "real",
        # A frase que impede a leitura errada do verde no CI.
        "mede_qualidade_juridica": not mock,
        "governanca": _governanca(casos),
        "agregado": agregar(resultados),
        "por_caso": resultados,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Régua das cinco capacidades de IA do EJC (I7)."
    )
    p.add_argument("--gold", default=GOLD_PADRAO)
    p.add_argument("--mock", action="store_true",
                   help="provedor falso determinístico (CI, sem rede/banco)")
    p.add_argument("--juiz", action="store_true",
                   help="modo real: adiciona LLM-juiz sobre os critérios")
    p.add_argument("--nivel", default=None,
                   help="modo real: nível de inteligência (padrão: piso da tarefa)")
    p.add_argument("--usuario", default=None,
                   help="modo real: e-mail do usuário sob o qual a régua roda "
                        "(padrão: papel jurídico mais alto ativo no banco)")
    p.add_argument("--out", default=RELATORIO_PADRAO)
    p.add_argument("--min-score", type=float, default=None,
                   help="falha se o score médio global ficar abaixo do piso")
    p.add_argument("--max-proibidos", type=int, default=None,
                   help="falha se mais que N casos contiverem conteúdo proibido")
    args = p.parse_args(argv)

    casos = carregar_gold(args.gold)
    if not casos:
        print(f"Nenhum caso em {args.gold}", file=sys.stderr)
        return 2

    resultados = asyncio.run(
        executar(casos, mock=args.mock, juiz=args.juiz, nivel=args.nivel,
                 usuario=args.usuario)
    )
    relatorio = montar_relatorio(casos, resultados, mock=args.mock, gold=args.gold)

    for r in resultados:
        marca = "OK  " if r["aprovado"] else "FALHA"
        extra = "  PROIBIDO" if r["conteudo_proibido"] else ""
        print(f"  [{marca}] {str(r['id']):26} {str(r['capacidade']):10} "
              f"score={r['score']:<6} crit={r['cobertura_criterios']:<6} "
              f"cit={r['cobertura_citacoes_tipo']}{extra}")

    ag = relatorio["agregado"]["global"]
    print("\n== AGREGADO ==")
    print(f"casos={ag['n']}  score_médio={ag['score_medio']}  "
          f"aprovados={ag['aprovados']}  "
          f"com_conteúdo_proibido={ag['casos_com_conteudo_proibido']}")
    print("\n== POR CAPACIDADE ==")
    for cap, b in relatorio["agregado"]["por_capacidade"].items():
        print(f"  {cap:12} n={b['n']:2}  score={b['score_medio']}")
    print("\n== POR ÁREA ==")
    for area, b in relatorio["agregado"]["por_area"].items():
        print(f"  {area:14} n={b['n']:2}  score={b['score_medio']}")

    gov = relatorio["governanca"]
    if gov["aviso"]:
        print(f"\nGOVERNANÇA: {gov['candidatos_nao_atestados']} caso(s) CANDIDATO(S) "
              f"e {gov['atestados_por_humano']} atestado(s). {gov['aviso']}")
    if args.mock:
        print("MODO MOCK: provedor falso — o resultado NÃO afere a qualidade "
              "jurídica de nenhuma capacidade.")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(relatorio, fh, ensure_ascii=False, indent=2)
        print(f"\nrelatório → {args.out}")

    falhas: list[str] = []
    if args.min_score is not None and ag["score_medio"] < args.min_score:
        falhas.append(f"score médio {ag['score_medio']} < piso {args.min_score}")
    if args.max_proibidos is not None and \
            ag["casos_com_conteudo_proibido"] > args.max_proibidos:
        falhas.append(
            f"{ag['casos_com_conteudo_proibido']} caso(s) com conteúdo proibido "
            f"> máximo {args.max_proibidos}"
        )
    if falhas:
        print("\nRÉGUA FALHOU:", file=sys.stderr)
        for f in falhas:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
