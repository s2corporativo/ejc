#!/usr/bin/env python3
"""Homologação real da IA jurídica com caso 100% fictício.

Cria cliente/caso marcados, confirma ficha de triagem, solicita petição inicial ao
pipeline SSE, salva a peça, executa validação jurídica/citações/HITL, tenta avançar
até `final` e testa PDF/DOCX. Não protocola e não usa dados reais.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pyotp

OUT = Path(os.getenv("EJC_QA_OUT", "qa/homologacao/reports"))
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "ia_peca_protocolavel_report.json"
PECA_TXT = OUT / "ia_peca_gerada_ficticia.txt"


def env(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise SystemExit(f"Variável obrigatória ausente: {nome}")
    return valor


def cpf_valido(base: int) -> str:
    nove = f"{base % 1_000_000_000:09d}"
    if len(set(nove)) == 1:
        nove = "123456789"
    nums = [int(x) for x in nove]
    s = sum(v * p for v, p in zip(nums, range(10, 1, -1)))
    nums.append((s * 10 % 11) % 10)
    s = sum(v * p for v, p in zip(nums, range(11, 1, -1)))
    nums.append((s * 10 % 11) % 10)
    return "".join(map(str, nums))


def detalhe(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        d = body.get("detail", body) if isinstance(body, dict) else body
        return json.dumps(d, ensure_ascii=False)[:1200] if not isinstance(d, str) else d[:1200]
    except Exception:
        return (resp.text or "")[:1200]


def req(client: httpx.Client, method: str, path: str, *, esperado: set[int] | None = None, **kwargs):
    inicio = time.perf_counter()
    resp = client.request(method, path, **kwargs)
    ms = round((time.perf_counter() - inicio) * 1000)
    if esperado is not None and resp.status_code not in esperado:
        raise RuntimeError(f"{method} {path}: {resp.status_code} — {detalhe(resp)}")
    return resp, ms


def parse_sse(resp: httpx.Response) -> tuple[list[dict[str, Any]], int | None]:
    eventos: list[dict[str, Any]] = []
    evento = None
    dados: list[str] = []
    t0 = time.perf_counter()
    ttfb = None
    for linha in resp.iter_lines():
        if ttfb is None and linha:
            ttfb = round((time.perf_counter() - t0) * 1000)
        if linha == "":
            if dados:
                raw = "\n".join(dados)
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {"raw": raw[:1000]}
                eventos.append({"event": evento or "message", "data": payload})
            evento, dados = None, []
            continue
        if linha.startswith("event:"):
            evento = linha.split(":", 1)[1].strip()
        elif linha.startswith("data:"):
            dados.append(linha.split(":", 1)[1].strip())
    return eventos, ttfb


def avaliar_texto(texto: str) -> dict[str, Any]:
    lower = texto.lower()
    secoes = {
        "enderecamento": bool(re.search(r"excelentíssim|juízo|juizado", lower)),
        "qualificacao": bool(re.search(r"qualifica|autor|requerente", lower)),
        "fatos": "dos fatos" in lower or "fatos" in lower,
        "direito": "do direito" in lower or "fundament" in lower,
        "tutela": "tutela" in lower,
        "pedidos": "dos pedidos" in lower or "requer" in lower,
        "valor_causa": "valor da causa" in lower,
        "fechamento": bool(re.search(r"termos em que|pede deferimento", lower)),
    }
    placeholders = re.findall(
        r"\[(?:nome|cpf|endereço|endereco|cidade|data|valor|oab|preencher)[^\]]*\]|"
        r"\b(?:xxx+|a preencher|inserir dados|complete aqui)\b",
        lower,
    )
    referencias = {
        "cdc": bool(re.search(r"código de defesa do consumidor|cdc|lei\s*8\.078", lower)),
        "lei_jec": bool(re.search(r"lei\s*(?:n[º°o.]*)?\s*9\.099", lower)),
        "cpc": bool(re.search(r"código de processo civil|cpc|lei\s*13\.105", lower)),
        "cc": bool(re.search(r"código civil|\bcc\b|lei\s*10\.406", lower)),
    }
    return {
        "caracteres": len(texto),
        "palavras": len(texto.split()),
        "secoes": secoes,
        "secoes_presentes": sum(secoes.values()),
        "placeholders": sorted(set(placeholders))[:30],
        "referencias_minimas": referencias,
        "aparenta_protocolavel_formalmente": (
            len(texto) >= 3500
            and sum(secoes.values()) >= 7
            and not placeholders
            and referencias["cdc"]
            and referencias["lei_jec"]
        ),
    }


def main() -> None:
    base = env("EJC_BASE_URL").rstrip("/")
    email = env("EJC_TEST_EMAIL")
    senha = env("EJC_TEST_PASSWORD")
    secret = env("EJC_TEST_TOTP_SECRET")
    suffix = str(time.time_ns())[-12:]
    marker = f"HOMOLOG-FICTICIO-IA-{suffix}"
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "marker": marker,
        "base_url": base,
        "etapas": [],
        "ids": {},
        "resultado": "INCOMPLETO",
    }

    with httpx.Client(base_url=base, timeout=180, follow_redirects=True) as client:
        # Login 2FA real.
        codigo = pyotp.TOTP(secret).now()
        login, ms = req(
            client, "POST", "/api/auth/login", esperado={200},
            json={"email": email, "password": senha, "totp_code": codigo},
        )
        token = login.json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
        report["etapas"].append({"etapa": "login_2fa", "status": login.status_code, "ms": ms})

        # Massa jurídica fictícia: negativação mantida depois de quitação.
        cliente_payload = {
            "tipo": "PF",
            "nome": f"{marker} Consumidor Teste",
            "cpf": cpf_valido(int(suffix)),
            "email": f"qa.{suffix}@homolog.com.br",
            "telefone": f"319{suffix[-8:]}",
            "cidade": "Betim",
            "estado": "MG",
            "observacoes": f"Massa exclusivamente fictícia da homologação {marker}.",
        }
        r, ms = req(client, "POST", "/api/clients/", esperado={201}, json=cliente_payload)
        client_id = r.json()["id"]
        report["ids"]["client_id"] = client_id
        report["etapas"].append({"etapa": "criar_cliente", "status": r.status_code, "ms": ms})

        fatos = (
            f"{marker}. Em 10/03/2026, o consumidor fictício celebrou contrato de internet "
            "residencial com a empresa fictícia Conecta Minas Telecom Ltda. Cancelou o serviço "
            "em 25/04/2026 e quitou a fatura final de R$ 189,90 em 30/04/2026, conforme comprovante. "
            "Apesar da quitação, em 20/05/2026 recebeu aviso de inscrição do seu nome em cadastro "
            "de inadimplentes pelo mesmo débito. Em 21/05/2026 enviou protocolo de atendimento e o "
            "comprovante; a empresa reconheceu o pagamento, mas não retirou a restrição. Em "
            "05/06/2026, nova consulta fictícia indicou que a negativação permanecia ativa. Não há "
            "outra inscrição anterior. A restrição impediu a contratação de crédito para aquisição "
            "de equipamento profissional. Documentos disponíveis: contrato, pedido de cancelamento, "
            "fatura, comprovante de pagamento, protocolo, resposta reconhecendo a quitação e consulta "
            "do cadastro restritivo. Pretende-se ajuizar ação no Juizado Especial Cível de Betim/MG, "
            "com tutela para exclusão imediata, declaração de inexistência do débito e indenização "
            "moderada por dano moral, sem inventar jurisprudência ou número de processo."
        )
        caso_payload = {
            "titulo": f"{marker} Negativação após quitação",
            "area": "consumidor",
            "prioridade": "alta",
            "parte_contraria": "Conecta Minas Telecom Ltda. — empresa fictícia",
            "valor_causa": "10189.90",
            "descricao_fatos": fatos,
            "client_id": client_id,
        }
        r, ms = req(client, "POST", "/api/cases/", esperado={201}, json=caso_payload)
        case_id = r.json()["id"]
        report["ids"]["case_id"] = case_id
        report["etapas"].append({"etapa": "criar_caso", "status": r.status_code, "ms": ms})

        ficha = {
            "case_id": case_id,
            "competencia": "Juizado Especial Cível da Comarca de Betim/MG",
            "rito": "Lei 9.099/1995",
            "legitimidade_ativa": "Consumidor fictício diretamente atingido pela negativação",
            "legitimidade_passiva": "Fornecedor fictício que manteve inscrição após reconhecer quitação",
            "prescricao_decadencia": "Demanda proposta dentro do prazo; conferir datas antes do protocolo",
            "tutela_urgencia": True,
            "tutela_fundamento": "Probabilidade demonstrada por comprovante e reconhecimento; perigo pela restrição ativa",
            "provas_disponiveis": "Contrato; cancelamento; fatura; comprovante; protocolos; resposta; consulta restritiva",
            "provas_faltantes": "Confirmar endereço completo das partes e documento atualizado da negativação",
            "valor_causa": "R$ 10.189,90",
            "risco_processual": "medio",
            "risco_nota": "Quantificação do dano moral e prova do impedimento de crédito exigem revisão humana",
            "pedidos_principais": "Tutela de exclusão; inexistência do débito; dano moral; inversão do ônus; citação",
            "pedidos_subsidiarios": "Multa diária proporcional em caso de descumprimento",
            "confirmar": True,
        }
        r, ms = req(client, "POST", "/api/triagem/ficha", esperado={200}, json=ficha)
        report["etapas"].append({"etapa": "confirmar_ficha_triagem", "status": r.status_code, "ms": ms})

        pedido = (
            "Gerar petição inicial completa, tecnicamente conservadora e pronta para revisão/protocolo "
            "no JEC de Betim/MG: tutela para exclusão em 48 horas, declaração de inexistência do débito, "
            "indenização por dano moral sugerida em R$ 10.000,00 ou valor prudente a ser arbitrado, "
            "inversão do ônus da prova, citação, custas apenas se cabíveis e demais consectários legais. "
            "Não inventar precedentes, números de processo, endereços, CPF ou OAB. Sinalizar qualquer "
            "lacuna factual que impeça protocolo imediato."
        )
        body = {
            "tipo_peca": "peticao_inicial",
            "area_direito": "consumidor",
            "nivel_complexidade": "juizado_especial",
            "flags_teses": ["dano_moral", "relacao_consumo", "hipossuficiencia", "prova_documental_suficiente", "pedido_tutela"],
            "descricao_fatos": fatos,
            "pedidos": pedido,
            "nomes_proteger": ["Consumidor Teste", "Conecta Minas Telecom Ltda."],
            "case_id": case_id,
            "instrucoes_adicionais": "Produzir versão completa, mas não preencher nem inventar dados ausentes.",
            "modo_producao": {
                "modo": "agente",
                "tipo_peca": "peticao_inicial",
                "area_direito": "consumidor",
                "instrucao_livre": pedido,
                "respostas_guiadas": {},
                "aprovado_para_redacao": True,
            },
        }
        inicio = time.perf_counter()
        with client.stream("POST", "/api/pecas/gerar", json=body, timeout=300) as stream:
            status = stream.status_code
            if status != 200:
                conteudo_erro = stream.read().decode("utf-8", "replace")[:2000]
                raise RuntimeError(f"IA gerar peça: HTTP {status}: {conteudo_erro}")
            eventos, ttfb = parse_sse(stream)
        total_ms = round((time.perf_counter() - inicio) * 1000)
        concluido = next((e["data"] for e in eventos if e["event"] == "concluido"), None)
        erros_sse = [e["data"] for e in eventos if e["event"] == "erro"]
        if not concluido:
            raise RuntimeError(f"SSE sem evento concluído; erros={erros_sse}; eventos={eventos[-5:]}")
        texto = concluido.get("documento") or ""
        PECA_TXT.write_text(texto, encoding="utf-8")
        report["etapas"].append({
            "etapa": "gerar_peca_ia_sse", "status": status, "ttfb_ms": ttfb,
            "total_ms": total_ms, "eventos": len(eventos), "caracteres": len(texto),
        })
        report["geracao"] = {
            "ai_log_id": concluido.get("ai_log_id"),
            "codigo_peca": concluido.get("codigo_peca"),
            "verificacao_citacoes": concluido.get("verificacao_citacoes"),
            "avaliacao_textual": avaliar_texto(texto),
        }

        # Persiste como rascunho IA e prova os gates até a versão final.
        r, ms = req(client, "POST", "/api/legal-docs/", esperado={201}, json={
            "titulo": f"{marker} Petição inicial JEC",
            "tipo_peca": "peticao_inicial",
            "conteudo": texto,
            "case_id": case_id,
            "ai_generated": True,
        })
        legal_doc_id = r.json()["id"]
        report["ids"]["legal_doc_id"] = legal_doc_id
        report["etapas"].append({"etapa": "salvar_peca_rascunho", "status": r.status_code, "ms": ms})

        # Bloqueio esperado antes de revisão/validação.
        r, ms = req(client, "PATCH", f"/api/legal-docs/{legal_doc_id}", esperado={422}, json={"status": "final"})
        report["etapas"].append({"etapa": "gate_final_sem_revisao", "status": r.status_code, "ms": ms, "detail": detalhe(r)})

        r, ms = req(client, "GET", f"/api/legal-docs/{legal_doc_id}/jurisprudencia-check", esperado={200})
        report["jurisprudencia_check"] = r.json()
        report["etapas"].append({"etapa": "check_jurisprudencia", "status": r.status_code, "ms": ms})

        r, ms = req(client, "POST", f"/api/legal-docs/{legal_doc_id}/validar", esperado={200})
        validacao = r.json()
        report["validacao_juridica"] = {
            "veredito": validacao.get("veredito"),
            "score_confianca": validacao.get("score_confianca"),
            "ai_log_id": validacao.get("ai_log_id"),
            "aviso": validacao.get("aviso"),
            "resposta_preview": (validacao.get("resposta") or "")[:3000],
        }
        report["etapas"].append({"etapa": "validar_peca", "status": r.status_code, "ms": ms})

        hitl_ok = False
        hitl_id = validacao.get("ai_log_id")
        if hitl_id:
            r, ms = req(client, "PATCH", f"/api/ai/logs/{hitl_id}/hitl", esperado={200, 409, 422, 503}, json={"status": "revisado"})
            hitl_ok = r.status_code == 200
            report["etapas"].append({"etapa": "hitl_validacao", "status": r.status_code, "ms": ms, "detail": detalhe(r)})
            try:
                c, cms = req(client, "GET", f"/api/ai/logs/{hitl_id}/citacoes", esperado={200, 503})
                report["citation_gate"] = c.json() if c.status_code == 200 else {"erro": detalhe(c)}
                report["etapas"].append({"etapa": "relatorio_citacoes_log", "status": c.status_code, "ms": cms})
            except Exception as exc:
                report["citation_gate"] = {"erro": str(exc)}

        final_ok = False
        if hitl_ok:
            r, ms = req(client, "PATCH", f"/api/legal-docs/{legal_doc_id}/aprovar", esperado={200, 422}, json={
                "observacoes": "Revisão humana fictícia de homologação: conferidos estrutura, pedidos e alertas; não representa aprovação para caso real."
            })
            report["etapas"].append({"etapa": "aprovar_peca", "status": r.status_code, "ms": ms, "detail": detalhe(r) if r.status_code != 200 else ""})
            if r.status_code == 200:
                r, ms = req(client, "PATCH", f"/api/legal-docs/{legal_doc_id}", esperado={200, 422}, json={"status": "final"})
                final_ok = r.status_code == 200
                report["etapas"].append({"etapa": "mover_para_final", "status": r.status_code, "ms": ms, "detail": detalhe(r) if r.status_code != 200 else ""})

        exportacoes = {}
        for nome, caminho, tipos in (
            ("pdf", f"/api/legal-docs/{legal_doc_id}/pdf", ("application/pdf",)),
            ("docx", f"/api/legal-docs/{legal_doc_id}/exportar-docx", ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream")),
        ):
            r, ms = req(client, "GET", caminho, esperado={200, 422, 500, 503})
            exportacoes[nome] = {
                "status": r.status_code,
                "ms": ms,
                "bytes": len(r.content),
                "content_type": r.headers.get("content-type"),
                "valido": r.status_code == 200 and len(r.content) > 500,
            }
            report["etapas"].append({"etapa": f"exportar_{nome}", **exportacoes[nome]})
        report["exportacoes"] = exportacoes
        report["resultado"] = "PRONTA_PARA_REVISAO_E_PROTOCOLO" if final_ok else "BLOQUEADA_PELOS_GATES"

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "resultado": report["resultado"],
        "marker": marker,
        "caracteres": report.get("geracao", {}).get("avaliacao_textual", {}).get("caracteres"),
        "score": report.get("validacao_juridica", {}).get("score_confianca"),
        "report": str(REPORT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        REPORT.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "resultado": "FALHA_EXECUCAO",
            "erro": f"{type(exc).__name__}: {exc}",
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        raise
