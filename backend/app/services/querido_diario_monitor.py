# ── app/services/querido_diario_monitor.py ───────────────────────────────────
# Monitoramento periódico de diários oficiais MUNICIPAIS (Querido Diário) →
# base de conhecimento, com curadoria humana obrigatória.
#
# POR QUE ESTE MÓDULO EXISTE
#
# O cliente do Querido Diário (`integrations/querido_diario_client.py`) já
# existia, mas só era alcançável sob demanda por endpoint — ninguém abre uma
# tela todo dia para perguntar se saiu algo no diário do município. O valor
# operacional da fonte é justamente o contrário: descobrir sozinho que saiu.
#
# DOIS MODOS DE ALVO
#
# 1. CONFIGURAÇÃO — municípios × termos declarados no `.env`. O achado entra
#    como conhecimento público (`client_id=None`).
# 2. RADAR VINCULADO (opt-in) — o termo é o NOME DO PRÓPRIO CLIENTE ativo,
#    pesquisado no município dele (derivado de `Client.cidade/estado` via a
#    API de localidades do IBGE). O achado fica vinculado àquele cliente.
#
# O vínculo do modo 2 é preciso por construção: ele vem da ORIGEM da consulta
# (o termo É o identificador do cliente), não de casar texto de diário com
# processo por heurística — que produziria vínculo errado, e num sistema
# jurídico vínculo errado é pior que vínculo nenhum.
#
# Em ambos os modos o achado nasce com `rag_status='pendente'` e a curadoria
# humana decide — igual ao caminho DJEN→RAG (`djen_service`).
#
# SIGILO PROFISSIONAL (por que o modo 2 tem dois interruptores)
#
# Pesquisar o nome de um cliente numa API pública de terceiro revela ao
# agregador que aquela pessoa se relaciona com o escritório. Razão social de
# PJ é registro público — risco baixo. Nome de PESSOA FÍSICA é dado pessoal, e
# "é cliente deste escritório" toca o sigilo profissional (EOAB art. 34, VII):
# por isso PF exige um segundo interruptor, explícito e desligado por padrão.
# CPF e CNPJ nunca são usados como termo de busca.
#
# NATUREZA DA FONTE (registrado porque tem consequência jurídica)
#
# O Querido Diário é agregador cívico, não a fonte que torna o ato
# juridicamente autêntico — o próprio cliente documenta isso. Por isso todo
# documento gravado aqui carrega a URL do diário de origem e o marcador de
# conferência obrigatória: o excerto NUNCA é prova autossuficiente.
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Pausa entre chamadas: a documentação da API recomenda uso razoável, na ordem
# de 60 req/min. 1,1 s mantém folga mesmo com municípios × termos grandes.
_PAUSA_ENTRE_CHAMADAS_S = 1.1

_CATEGORIA = "diario_oficial_municipal"


def _csv(valor: str | None) -> list[str]:
    return [p.strip() for p in (valor or "").split(",") if p.strip()]


@dataclass(frozen=True)
class Alvo:
    """Uma consulta a fazer: município × termo, com o vínculo que a originou.

    `client_id` não é palpite: quando existe, é o cliente cujo PRÓPRIO nome
    virou o termo pesquisado. O vínculo vem da origem da consulta, não de casar
    texto de diário com processo por heurística — que é o que produziria
    vínculo errado.
    """

    codigo_ibge: str
    termo: str
    client_id: str | None = None
    origem: str = "configuracao"


async def _alvos_de_clientes(db: AsyncSession, resultado: dict) -> list[Alvo]:
    """Deriva alvos a partir dos clientes ativos (radar vinculado).

    SIGILO PROFISSIONAL — a razão do recorte por tipo de cliente:
    pesquisar o nome de um cliente numa API pública de terceiro revela ao
    agregador que aquela pessoa se relaciona com o escritório. Para PJ, razão
    social é registro público e o risco é baixo. Para PESSOA FÍSICA, o nome é
    dado pessoal e a informação "é cliente deste escritório" toca o sigilo
    profissional (EOAB art. 34, VII) — por isso PF exige uma segunda opção,
    explícita e desligada por padrão. CPF NUNCA é usado como termo.
    """
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.integrations import feature_flags
    from app.integrations.ibge_localidades_client import (
        IbgeLocalidadesClient,
        IbgeLocalidadesError,
    )
    from app.models.client import Client, ClientStatus, ClientTipo

    s = get_settings()
    incluir_pf = bool(getattr(s, "QUERIDO_DIARIO_RADAR_INCLUI_PF", False))

    if not feature_flags.enabled("ibge"):
        # Sem IBGE não há como transformar "Betim/MG" em código de município.
        resultado["erros"]["ibge_desabilitado"] = 1
        return []

    tipos = [ClientTipo.PJ] if not incluir_pf else [ClientTipo.PJ, ClientTipo.PF]
    linhas = (
        await db.execute(
            select(Client.id, Client.tipo, Client.nome, Client.razao_social,
                   Client.nome_fantasia, Client.cidade, Client.estado)
            .where(
                Client.deleted_at.is_(None),
                Client.status == ClientStatus.ativo,
                Client.tipo.in_(tipos),
                Client.cidade.isnot(None),
                Client.estado.isnot(None),
            )
        )
    ).all()

    ibge = IbgeLocalidadesClient()
    cache: dict[tuple[str, str], str | None] = {}
    alvos: list[Alvo] = []

    for cid, tipo, nome, razao, fantasia, cidade, uf in linhas:
        # Para PJ o termo sai SÓ de razão social / nome fantasia. Cair para
        # `Client.nome` seria um furo no recorte de sigilo: `razao_social` não
        # é obrigatória no backend (só um `*` no formulário React), então um
        # registro `tipo=PJ` criado por API ou importação pode carregar o nome
        # de uma pessoa natural em `nome` — que iria para a API pública mesmo
        # com QUERIDO_DIARIO_RADAR_INCLUI_PF desligado. O gate é por `tipo`;
        # sem isto, a PROCEDÊNCIA do campo escapava do gate.
        if tipo == ClientTipo.PJ:
            termo = (razao or fantasia or "").strip()
            if not termo:
                resultado["erros"]["cliente_sem_razao_social"] = (
                    resultado["erros"].get("cliente_sem_razao_social", 0) + 1
                )
                continue
        else:
            termo = (nome or "").strip()

        # Termo curto casa com meio diário: 4 caracteres é o piso que o próprio
        # serviço de conflito usa para busca por nome.
        if len(termo) < 4:
            continue

        chave = ((cidade or "").strip(), (uf or "").strip().upper())
        if chave not in cache:
            try:
                municipio = await ibge.canonicalizar(chave[0], chave[1])
                cache[chave] = str(municipio["id"]) if municipio else None
            except (IbgeLocalidadesError, ValueError, KeyError):
                cache[chave] = None
                resultado["erros"]["municipio_nao_canonicalizado"] = (
                    resultado["erros"].get("municipio_nao_canonicalizado", 0) + 1
                )
        codigo = cache[chave]
        if not codigo:
            continue

        alvos.append(Alvo(codigo_ibge=codigo, termo=termo,
                          client_id=cid, origem="cliente"))

    # Teto por execução. Sem ele, o escritório transfere a base INTEIRA de
    # razões sociais ao agregador todo dia — e o padrão de consultas
    # reconstrói a carteira do lado de lá, que é por acumulação o mesmo risco
    # que a flag de PF contém caso a caso. O corte é determinístico (ordem da
    # query) e fica contabilizado no resultado.
    teto = int(getattr(s, "QUERIDO_DIARIO_RADAR_MAX_CLIENTES", 50) or 50)
    if len(alvos) > teto:
        resultado["alvos_de_clientes_cortados"] = len(alvos) - teto
        alvos = alvos[:teto]

    return alvos


def _chave_origem(codigo_ibge: str, url: str) -> str:
    """Chave de dedup: a URL do diário identifica a edição de forma estável.

    Inclui o código IBGE porque a mesma edição pode ser devolvida em consultas
    de termos diferentes — o dedup de `upsert_documento` colapsa as repetições.
    """
    return f"querido_diario:{codigo_ibge}:{url}"


def _montar_documento(
    codigo_ibge: str,
    termo: str,
    item: dict[str, Any],
    *,
    client_id: str | None = None,
    origem: str = "configuracao",
) -> dict | None:
    """Projeta um resultado da API no contrato de `upsert_documento`.

    Devolve None quando o item não traz o mínimo para ser auditável (URL de
    origem e algum texto) — documento sem origem conferível não entra na base.
    """
    url = (item.get("url") or item.get("file_url") or "").strip()
    excertos = [e.strip() for e in (item.get("excerpts") or []) if e and e.strip()]
    if not url or not excertos:
        return None

    data_pub = (item.get("date") or "").strip()
    territorio = (item.get("territory_name") or "").strip()
    uf = (item.get("state_code") or "").strip()
    rotulo_local = " / ".join(p for p in (territorio, uf) if p) or codigo_ibge

    conteudo = "\n\n".join(excertos)
    titulo = f"Diário Oficial de {rotulo_local}"
    if data_pub:
        titulo = f"{titulo} — {data_pub}"

    return {
        "titulo": titulo[:500],
        "categoria": _CATEGORIA,
        "conteudo": conteudo,
        "chave_origem": _chave_origem(codigo_ibge, url),
        "fonte": url,
        # Vínculo com o cliente cujo nome originou a consulta. Quando presente,
        # o documento passa a ser material DAQUELE cliente no RAG (isolamento
        # por client_id), e não acervo público.
        "client_id": client_id,
        "extra": {
            "rag_status": "pendente",
            "tipo_fonte": "diario_oficial_municipal",
            "origem_captura": "querido_diario_monitor",
            "origem_alvo": origem,
            "codigo_ibge": codigo_ibge,
            "termo_monitorado": termo,
            "data_publicacao": data_pub,
            "municipio": territorio,
            "uf": uf,
            # O agregador não autentica o ato: a conferência no diário oficial
            # de origem é obrigatória antes de qualquer uso jurídico.
            "natureza": "agregador_secundario",
            "conferencia_original_obrigatoria": True,
        },
    }


async def executar_monitoramento(db: AsyncSession) -> dict[str, Any]:
    """Varre municípios × termos configurados e ingere os achados.

    Devolve um dicionário de RESULTADO (não um "ok" mudo): quantos municípios e
    termos foram consultados, quantos achados vieram, quantos documentos novos
    entraram e quais consultas falharam. É esse dicionário que vai para o
    heartbeat — monitorar resultado, não execução (achado V2-3.1).
    """
    from app.core.config import get_settings
    from app.integrations import feature_flags
    from app.integrations.querido_diario_client import (
        QueridoDiarioClient,
        QueridoDiarioError,
    )
    from app.services import ingestion_service

    s = get_settings()
    municipios = _csv(getattr(s, "QUERIDO_DIARIO_MONITOR_MUNICIPIOS", ""))
    termos = _csv(getattr(s, "QUERIDO_DIARIO_MONITOR_TERMOS", ""))
    janela = max(1, int(getattr(s, "QUERIDO_DIARIO_MONITOR_JANELA_DIAS", 2)))

    resultado: dict[str, Any] = {
        "municipios": len(municipios),
        "termos": len(termos),
        "consultas": 0,
        "achados": 0,
        "novos": 0,
        "atualizados": 0,
        "alvos_de_clientes": 0,
        "erros": {},
    }

    # A flag da integração vale também para o job: ligar o monitor sem ligar a
    # fonte seria contornar o gate por um caminho lateral.
    if not feature_flags.enabled("querido_diario"):
        resultado["erros"]["integracao_desabilitada"] = 1
        return resultado

    # Alvos por configuração: município × termo declarados no .env.
    alvos = [
        Alvo(codigo_ibge=municipio, termo=termo)
        for municipio in municipios
        for termo in termos
    ]

    # Alvos vinculados: o nome do próprio cliente ativo, no município dele.
    if getattr(s, "QUERIDO_DIARIO_RADAR_CLIENTES_ENABLED", False):
        vinculados = await _alvos_de_clientes(db, resultado)
        resultado["alvos_de_clientes"] = len(vinculados)
        alvos.extend(vinculados)

    if not alvos:
        # Rodar sem nenhum alvo é o modo mais traiçoeiro de falhar: o job
        # termina "ok" tendo consultado nada. Vira erro visível.
        resultado["erros"]["configuracao_incompleta"] = 1
        return resultado

    hoje = date.today()
    inicio = hoje - timedelta(days=janela)
    cliente = QueridoDiarioClient()

    for indice, alvo in enumerate(alvos):
        if indice:
            await asyncio.sleep(_PAUSA_ENTRE_CHAMADAS_S)
        resultado["consultas"] += 1
        try:
            payload = await cliente.buscar(
                codigo_ibge=alvo.codigo_ibge,
                termo=alvo.termo,
                data_inicio=inicio,
                data_fim=hoje,
            )
        except (QueridoDiarioError, ValueError) as exc:
            chave = type(exc).__name__
            resultado["erros"][chave] = resultado["erros"].get(chave, 0) + 1
            logger.warning(
                "[QueridoDiário] consulta %s/%s falhou: %s",
                alvo.codigo_ibge, alvo.origem, chave,
            )
            continue

        itens = payload.get("gazettes") or []
        resultado["achados"] += len(itens)
        for item in itens:
            doc = _montar_documento(
                alvo.codigo_ibge, alvo.termo, item,
                client_id=alvo.client_id, origem=alvo.origem,
            )
            if not doc:
                continue
            try:
                # Savepoint: um documento problemático não derruba a varredura.
                async with db.begin_nested():
                    estado = await ingestion_service.upsert_documento(
                        db, embutir_vetores=False, **doc
                    )
                if estado == "novo":
                    resultado["novos"] += 1
                elif estado == "atualizado":
                    resultado["atualizados"] += 1
            except Exception as exc:  # noqa: BLE001 — um item não para o job
                chave = f"ingestao_{type(exc).__name__}"
                resultado["erros"][chave] = resultado["erros"].get(chave, 0) + 1

    await db.commit()
    return resultado
