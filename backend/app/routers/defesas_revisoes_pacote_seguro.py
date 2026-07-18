"""Pacote jurídico seguro para Defesas e Revisões.

Este router é incluído antes do router avançado para substituir a implementação
legada de ``POST /defesas-revisoes/avancado/pacote``. Relatórios diagnósticos
podem ser criados em qualquer nível de prontidão, mas documentos executivos,
procuração e contrato de honorários permanecem bloqueados enquanto houver
pendência impeditiva.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.user import User
from app.routers.defesas_revisoes import MODALIDADES
from app.routers.defesas_revisoes_avancado import (
    _dict,
    _exigir_advogado,
    _markdown_resultado,
    _matriz_teses,
    _resultado_completude,
)
from app.services.geracao_documental import gerar_kit_inicial

router = APIRouter(
    prefix="/defesas-revisoes/avancado",
    tags=["Defesas e Revisões — pacote seguro"],
)


def _lista(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _texto_cronologia(resultado: dict[str, Any]) -> str:
    linhas = ["# Cronologia documental", "", "Rascunho sujeito à revisão humana.", ""]
    eventos = _lista(resultado.get("datas_eventos"))
    if not eventos:
        linhas.append("Nenhum evento cronológico foi confirmado automaticamente.")
    for item in eventos:
        if not isinstance(item, dict):
            continue
        evento = item.get("evento") or "Evento a confirmar"
        data = item.get("data") or "data não confirmada"
        origem = item.get("documento") or item.get("fonte") or "origem não informada"
        pagina = item.get("pagina")
        trecho = item.get("origem_literal") or item.get("trecho_literal")
        linhas.append(f"## {data} — {evento}")
        linhas.append(f"- Origem: {origem}{f', página {pagina}' if pagina else ''}")
        if trecho:
            linhas.append(f"- Trecho literal: {trecho}")
        linhas.append("")
    return "\n".join(linhas)[:60000]


def _texto_checklist(resultado: dict[str, Any]) -> str:
    linhas = ["# Checklist documental e jurídico", "", "Rascunho sujeito à revisão humana.", ""]
    checklist = _lista(resultado.get("checklist_obrigatorio"))
    faltantes = _lista(resultado.get("documentos_faltantes"))
    if not checklist and not faltantes:
        linhas.append("Nenhuma pendência foi estruturada; confirme manualmente o conjunto documental.")
    for item in checklist:
        if isinstance(item, dict):
            status = str(item.get("status") or "confirmar")
            marcador = "x" if status == "atendido" else " "
            nome = item.get("item") or item.get("titulo") or "Verificação jurídica"
            impeditivo = " — impeditivo" if item.get("impeditivo") else ""
            linhas.append(f"- [{marcador}] {nome} ({status}){impeditivo}")
        else:
            linhas.append(f"- [ ] {item}")
    if faltantes:
        linhas.extend(["", "## Documentos faltantes"])
        linhas.extend(f"- [ ] {item}" for item in faltantes)
    return "\n".join(linhas)[:60000]


def _texto_indice_anexos(resultado: dict[str, Any]) -> str:
    linhas = ["# Índice dos anexos", "", "A ordem deve ser conferida antes do protocolo.", ""]
    documentos = _lista(resultado.get("documentos_importados")) or _lista(resultado.get("documentos"))
    if not documentos:
        linhas.append("Nenhum documento foi relacionado ao diagnóstico.")
    for ordem, item in enumerate(documentos, 1):
        if not isinstance(item, dict):
            linhas.append(f"{ordem}. {item}")
            continue
        nome = item.get("filename") or item.get("nome") or f"Documento {ordem}"
        classificacao = _dict(item.get("classification") or item.get("classificacao"))
        tipo = classificacao.get("nome") or classificacao.get("tipo") or "não classificado"
        paginas = item.get("page_count") or len(_lista(item.get("paginas"))) or "?"
        linhas.append(f"{ordem}. {nome} — {tipo} — {paginas} página(s)")
    return "\n".join(linhas)[:60000]


def _texto_caderno_provas(resultado: dict[str, Any]) -> str:
    linhas = ["# Caderno de provas", "", "Relação estruturada; a autenticidade e pertinência devem ser confirmadas.", ""]
    provas: list[str] = []
    for item in _matriz_teses(resultado):
        for prova in _lista(item.get("provas")):
            valor = str(prova).strip()
            if valor and valor not in provas:
                provas.append(valor)
    if not provas:
        linhas.append("Nenhuma prova foi vinculada de forma estruturada às teses.")
    else:
        for ordem, prova in enumerate(provas, 1):
            linhas.append(f"{ordem}. {prova}")
    return "\n".join(linhas)[:60000]


def _texto_memoria_calculo(resultado: dict[str, Any]) -> str:
    dados = _dict(resultado.get("juros_taxas") or resultado.get("dados_bancarios"))
    return (
        "# Memória preliminar de cálculo\n\n"
        "Os valores abaixo foram extraídos ou informados e não constituem conclusão de abusividade. "
        "Recalcule no motor determinístico antes de utilizar em peça.\n\n"
        f"```json\n{json.dumps(dados, ensure_ascii=False, indent=2)}\n```"
    )[:60000]


def planejar_pacote(modalidade: str, resultado: dict[str, Any]) -> dict[str, Any]:
    """Plano puro usado pelo endpoint e por testes de regressão."""
    if modalidade not in MODALIDADES:
        raise ValueError("Modalidade inválida")
    completude = _resultado_completude(resultado)
    documentos = [
        {"codigo": "relatorio", "titulo": "Relatório de Diagnóstico", "tipo": PecaTipo.parecer},
        {"codigo": "cronologia", "titulo": "Cronologia Documental", "tipo": PecaTipo.parecer},
        {"codigo": "matriz", "titulo": "Matriz de Vícios e Teses", "tipo": PecaTipo.parecer},
        {"codigo": "checklist", "titulo": "Checklist Documental e Jurídico", "tipo": PecaTipo.parecer},
        {"codigo": "indice", "titulo": "Índice dos Anexos", "tipo": PecaTipo.parecer},
        {"codigo": "provas", "titulo": "Caderno de Provas", "tipo": PecaTipo.parecer},
    ]
    if modalidade == "revisao_bancaria":
        documentos.append({"codigo": "calculo", "titulo": "Memória Preliminar de Cálculo", "tipo": PecaTipo.parecer})
    return {
        "completude": completude,
        "documentos_diagnosticos": documentos,
        "gerar_kit_inicial": bool(completude["pode_gerar_peca"]),
        "liberar_motor_peca": bool(completude["pode_gerar_peca"]),
        "motivo_bloqueio": None if completude["pode_gerar_peca"] else (
            "Documentos obrigatórios ou itens impeditivos permanecem pendentes. "
            "Relatórios podem ser preparados, mas peça, procuração e honorários ficam bloqueados."
        ),
    }


def _conteudo_por_codigo(codigo: str, modalidade: str, resultado: dict[str, Any]) -> str:
    if codigo == "relatorio":
        return _markdown_resultado(modalidade, resultado)
    if codigo == "cronologia":
        return _texto_cronologia(resultado)
    if codigo == "matriz":
        return "# Matriz de Vícios e Teses\n\n" + json.dumps(_matriz_teses(resultado), ensure_ascii=False, indent=2)
    if codigo == "checklist":
        return _texto_checklist(resultado)
    if codigo == "indice":
        return _texto_indice_anexos(resultado)
    if codigo == "provas":
        return _texto_caderno_provas(resultado)
    if codigo == "calculo":
        return _texto_memoria_calculo(resultado)
    return "# Documento estratégico\n\nConteúdo pendente de revisão."


@router.post("/pacote", dependencies=[Depends(rate_limit("defesas-pacote-seguro", 5))])
async def gerar_pacote_seguro(
    body: dict,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_advogado(cu)
    case_id = str(body.get("case_id") or "")
    modalidade = str(body.get("modalidade") or "")
    resultado = _dict(body.get("resultado"))
    if not case_id or modalidade not in MODALIDADES or not resultado:
        raise HTTPException(422, "Caso, modalidade e resultado são obrigatórios")

    caso = await verificar_acesso_caso(db, cu, case_id)
    cliente = await db.get(Client, caso.client_id)
    if not cliente:
        raise HTTPException(422, "Cliente do caso não localizado")

    plano = planejar_pacote(modalidade, resultado)
    criados: list[dict[str, Any]] = []
    for especificacao in plano["documentos_diagnosticos"]:
        titulo = f"{especificacao['titulo']} — {caso.titulo}"[:255]
        documento = LegalDoc(
            id=str(uuid4()),
            titulo=titulo,
            tipo_peca=especificacao["tipo"],
            status=PecaStatus.rascunho,
            conteudo=_conteudo_por_codigo(especificacao["codigo"], modalidade, resultado)[:60000],
            versao=1,
            area=MODALIDADES[modalidade]["area"],
            ai_generated=True,
            human_reviewed=False,
            case_id=case_id,
            created_by=cu.id,
        )
        db.add(documento)
        criados.append({
            "id": documento.id,
            "codigo": especificacao["codigo"],
            "titulo": documento.titulo,
            "tipo": especificacao["tipo"].value,
            "status": "rascunho",
        })

    kit: dict[str, Any]
    if plano["gerar_kit_inicial"]:
        kit = await gerar_kit_inicial(
            db,
            caso,
            cliente,
            cu,
            tipo_poderes="ad_judicia",
            permite_substabelecimento=False,
        )
    else:
        kit = {
            "status": "bloqueado",
            "motivo": plano["motivo_bloqueio"],
            "procuracao": None,
            "contrato_honorarios": None,
        }

    await db.commit()
    return {
        "kit_documental": kit,
        "documentos_estrategicos": criados,
        "completude": plano["completude"],
        "peca_bloqueada": not plano["liberar_motor_peca"],
        "motor_peca_liberado": plano["liberar_motor_peca"],
        "motivo_bloqueio": plano["motivo_bloqueio"],
        "aviso": (
            "Relatórios e cadernos foram criados como rascunho. "
            "Peça principal deve seguir pelo Motor de Peça e toda saída exige revisão humana."
        ),
    }
