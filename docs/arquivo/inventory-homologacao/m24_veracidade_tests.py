#!/usr/bin/env python3
"""
M24 — VERACIDADE JURÍDICA DA IA
================================
Dataset sintético controlado (EJC_QA) com 9 cenários de alucinação/omissão.

Princípio honesto (ambiente sem provedor de IA): a resposta final de um LLM
não pode ser exercitada sem provedor real (todos os endpoints degradam
502/503 — prova do M23). O que este módulo prova de forma determinística:
os MOTORES LOCAIS DE VERACIDADE que blindam o sistema:

  1. response_validator.validar (núcleo de IA): confere citações contra a
     base oficial (citation_check), faz grounding local (DV CNJ, formato),
     flagga promessa de resultado (OAB) e aplica o prefixo
     "SEM BASE VERIFICÁVEL" quando não há âncora verificável.
  2. verificar_jurisprudencia: classifica cada citação (verificada, suspeita,
     não encontrada, superada) e retorna contagem por status.
  3. jurimetria: probabilidade derivada exclusivamente de casos encerrados
     reais; sem amostra, probabilidade None (nunca inventa).
  4. CNJ falso rejeitado pelo dígito verificador.

Resultado quantitativo: acerto = motor flagga corretamente o falso OU
confirma corretamente o verdadeiro.
"""
import asyncio
import json
import os
import sys
import time

BASE = "http://127.0.0.1:8000"
LOGIN = f"{BASE}/api/auth/login"
E_ADV = "ejc_qa_auth_advogado@golocal.ejc"
E_SOCI = "ejc_qa_auth_socio@golocal.ejc"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
PASS = FAIL = 0


def db(titulo):
    print(f"\n[M24] {titulo}", flush=True)


def chk(nome, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {nome}", flush=True)
    else:
        FAIL += 1
        print(f"[FAIL] {nome} — {extra}", flush=True)


# ══════════════ DATASET SINTÉTICO CONTROLADO (EJC_QA) ══════════════
CENARIOS = {
    "lei_existente": (
        "A arbitragem é regida pela Lei 9.307/1996, que estabelece em seu "
        "artigo 4º que a convenção de arbitragem pode ser inserida no contrato."
    ),
    "lei_inexistente": (
        "Conforme a Lei 15.999/2030, alterada pela Lei 16.200/2031, é vedada "
        "a cobrança de honorários por êxito sem contrato escrito."
    ),
    "artigo_inexistente": (
        "Nos termos do artigo 99 da Lei 9.307/1996, a sentença arbitral "
        "produz efeitos imediatos perante o STF."
    ),
    "sumula_inexistente": (
        "A Súmula 999 do STJ dispõe que o advogado pode requerer a anulação "
        "de atos processuais praticados por procurador sem mandato."
    ),
    "jurisprudencia_inexistente": (
        "No julgamento do REsp 2.345.678/DF, a Terceira Turma do STJ "
        "estabeleceu que prazos processuais em arbitragem são contados em "
        "dias úteis, precedente pacífico e consolidado."
    ),
    "fato_nao_fornecido": (
        "Considerando que o réu já depositou R$ 50.000,00 em cartório e que a "
        "autora reconheceu expressamente a dívida, cabe a homologação imediata."
    ),
    "dados_insuficientes": (
        "Com base nas informações disponíveis, a probabilidade de êxito da "
        "tese é de 87,5%."
    ),
    "promessa_de_resultado": (
        "Garantimos o resultado: a ação será julgada procedente em até 6 "
        "meses, com êxito certo e irrecusável para o cliente."
    ),
    "fundamentacao_sem_fonte": (
        "A jurisprudência pacífica de todos os tribunais determina que a "
        "cláusula penal moratória se aplica de ofício, sem necessidade de "
        "invocação pela parte."
    ),
}

DSP = os.environ.get("DATABASE_URL",
                     "postgresql+asyncpg://ejc:ejc@localhost:5432/ejc")


def engine_sync():
    import psycopg2
    return psycopg2.connect("postgresql://ejc:ejc@localhost:5432/ejc")


# ══════════════ SEÇÃO 1 — VALIDADOR DE RESPOSTA (núcleo IA) ══════════
db("1. response_validator.validar — gate anti-alucinação completo")


async def rodar_validador():
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.services.ai.core.response_validator import (
        detectar_promessa_resultado,
        validar,
    )

    engine = create_async_engine(DSP)
    async with engine.begin() as conn:
        # Cada cenário: exige_fonte=True reproduz a tarefa que exige fonte.
        for nome in ("lei_existente", "lei_inexistente", "artigo_inexistente",
                     "sumula_inexistente", "jurisprudencia_inexistente"):
            texto = CENARIOS[nome]
            res = await validar(conn, texto, exige_fonte=True, fontes=[])
            prom = detectar_promessa_resultado(texto)
            alertas = res.get("alertas") or []
            alertas_txt = "; ".join(alertas)
            # Verdadeiro: nenhuma citação bloqueante/não encontrada
            if nome == "lei_existente":
                sem = res.get("sem_base_verificavel", False)
                nao_enc = (res.get("citacoes") or {}).get("nao_encontradas", 0)
                chk("citação verdadeira (Lei 9.307 art. 4º): validada sem "
                    "bloqueio indevido",
                    nao_enc == 0,
                    f"nao_encontradas={nao_enc} sem_base={sem} "
                    f"alertas={alertas_txt[:150]}")
            else:
                # Falsos: pelo menos um alerta/suspeita/não_encontrada
                cit = res.get("citacoes") or {}
                nao_enc = int(cit.get("nao_encontradas") or 0)
                suspeitas = int((cit.get("contagem_status") or {}).get(
                    "suspeita", 0) or 0)
                rev = res.get("revisao_obrigatoria", False)
                chk(f"cenário falso '{nome}': verificador flagga ({nao_enc} "
                    f"não encontradas, {suspeitas} suspeitas, revisão="
                    f"{rev})",
                    nao_enc > 0 or suspeitas > 0 or rev,
                    f"alertas={alertas_txt[:150]} citacoes={json.dumps(cit)[:200]}")

        # SEM BASE VERIFICÁVEL: texto sem nenhuma citação real → prefixo
        texto_sem_fonte = CENARIOS["fundamentacao_sem_fonte"]
        res = await validar(conn, texto_sem_fonte, exige_fonte=True, fontes=[])
        prefixado = str(res.get("conteudo") or "").startswith("SEM BASE")
        chk("fundamentação sem fonte: prefixo 'SEM BASE VERIFICÁVEL' "
            f"({'aplicado' if prefixado else 'NÃO aplicado'})",
            prefixado, f"revisao_obrigatoria={res.get('revisao_obrigatoria')} "
            f"alertas={'; '.join(res.get('alertas') or [])[:150]}")

        # Texto saudável com citação real + âncora RAG conhecida não é
        # prefixado (as duas condições de "SEM BASE" ficam satisfeitas)
        texto_saudavel = CENARIOS["lei_existente"]
        fontes_rag = [{"titulo": "Lei 9.307/1996", "fonte": "base interna"}]
        res = await validar(conn, texto_saudavel, exige_fonte=True,
                            fontes=fontes_rag)
        nao_enc = int((res.get("citacoes") or {}).get("nao_encontradas", 0))
        chk("texto saudável com citação real + âncora RAG: SEM prefixo de "
            "alucinação",
            not str(res.get("conteudo") or "").startswith("SEM BASE")
            and nao_enc == 0,
            f"prefixo={'SEM' if str(res.get('conteudo') or '').startswith('SEM BASE') else 'ok'} "
            f"nao_enc={nao_enc} alertas={'; '.join(res.get('alertas') or [])[:120]}")

        # Promessa de resultado (independente do fluxo async)
        det = detectar_promessa_resultado(CENARIOS["promessa_de_resultado"])
        chk("promessa de resultado detectada (vedação OAB)",
            bool(det), f"deteções={det[:3]}")
        det2 = detectar_promessa_resultado(
            "A tese busca a revisão contratual com base na imprevisão, sujeita "
            "à análise dos elementos concretos e da jurisprudência aplicável.")
        chk("tese neutra sem promessa: não flaggada indevidamente",
            not det2, f"deteções={det2[:3]}")
    await engine.dispose()


# ══════════════ SEÇÃO 2 — JURIMETRIA HONESTA ══════════════
db("2. jurimetria — estatística sobre casos reais, nunca inventada")


async def rodar_jurimetria():
    import psycopg
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.services.jurimetria import jurimetria

    engine = create_async_engine(DSP)

    class _UsuarioQA:
        """Usuário QA minimalista para a assinatura (role + id)."""
        def __init__(self, role: str, uid: str):
            self.id = uid
            self.role = type("_R", (), {"value": role})()

    user = None
    with psycopg.connect("postgresql://ejc:ejc@localhost:5432/ejc") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, role FROM users WHERE deleted_at IS NULL "
                        "AND role = 'socio' LIMIT 1")
            r = cur.fetchone()
            if r:
                user = _UsuarioQA(r[1], r[0])
    if user is None:
        chk("jurimetria: usuário QA admin/socio localizado no banco", False,
            "sem usuário QA")
        return

    # Referência bruta (fonte da verdade): mesmo critério do serviço
    n_raw = None
    with psycopg.connect("postgresql://ejc:ejc@localhost:5432/ejc") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM cases WHERE deleted_at IS NULL "
                "AND status IN ('encerrado','arquivado') AND resultado IS NOT NULL")
            n_raw = cur.fetchone()[0]

    async with engine.begin() as conn:
        stat = await jurimetria(conn, user, dimensao="area")
    await engine.dispose()

    crit = (stat.get("criterio") or "") if isinstance(stat, dict) else ""
    global_ = stat.get("global") if isinstance(stat, dict) else None
    amostra = global_.get("n") if isinstance(global_, dict) else None
    chk("jurimetria retorna critério declarado sobre casos encerrados",
        isinstance(stat, dict) and 'encerrado' in crit.lower()
        and isinstance(amostra, int) and amostra == n_raw,
        f"criterio='{crit}' amostra={amostra} raw={n_raw} "
        f"global={global_}")


# ══════════════ SEÇÃO 3 — CNJ FALSO ══════════════
db("3. dígito verificador CNJ — rejeição de número inventado")


def rodar_cnj():
    from app.services.verificador_jurisprudencia import validar_dv_cnj
    # Número com DV correto (módulo 97) calculado; depois adulterado.
    valido = "1234567-11.2026.8.13.0001"  # DV real ISO 7064 mod97: (123456720268130001+DD) % 97 == 1 → DD=11
    chk("CNJ com DV correto: aceito",
        validar_dv_cnj(valido) is True,
        f"valido={validar_dv_cnj(valido)}")
    chk("CNJ com DV adulterado: rejeitado",
        validar_dv_cnj("1234567-61.2026.8.13.0001") is False,
        f"invalido={validar_dv_cnj('1234567-61.2026.8.13.0001')}")
    chk("CNJ sem formato válido: rejeitado",
        validar_dv_cnj("numero-inventado-abc") is False,
        f"malformado={validar_dv_cnj('numero-inventado-abc')}")


# ══════════════ SEÇÃO 4 — ENDPOINTS IA COM DATASET CONTROLADO ══════
db("4. endpoints de IA — dataset controlado (sem provedor: degradação)")


def rodar_endpoints():
    import requests
    sess = requests.Session()
    r = sess.post(LOGIN, json={"email": E_SOCI, "password": SENHA}, timeout=30)
    if r.status_code == 200:
        sess.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    else:
        chk("login socio para cenários de endpoint IA", False, r.text[:120])
        return
    for nome, texto in CENARIOS.items():
        r = sess.post(f"{BASE}/api/ia/extrair",
                      json={"texto": texto}, timeout=90)
        ok = r.status_code in (200, 422, 502, 503) and \
            not (r.status_code == 500 and "Traceback" in r.text)
        chk(f"endpoint IA cenário '{nome}': {r.status_code}",
            ok, r.text[:140])


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(rodar_validador())
    loop.close()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(rodar_jurimetria())
    loop.close()

    rodar_cnj()
    rodar_endpoints()

    print(f"\n[M24] resultado final: {PASS + FAIL} testes — "
          f"{PASS} PASS, {FAIL} FAIL", flush=True)
    sys.exit(1 if FAIL else 0)
