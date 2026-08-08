"""Regressões P0 da conversão Sala/Raio-X → caso oficial.

Cobre:
- UUID de cliente de outra carteira não pode ser usado;
- deduplicação por CPF não pode devolver/vincular cliente alheio;
- preview preserva o alerta sem expor id/nome da carteira protegida;
- conversão autorizada cria CaseIntelligenceSnapshot de origem ``raio_x`` na
  mesma operação, não aprovado e versionado.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from app.schemas.raio_x import CasoConversao, ClienteConversao, RaioXConverterRequest


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Raio-X Teste', :role, true)"
        ),
        {"id": uid, "email": f"raiox-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _carregar_user(db, user_id: str):
    from app.models.user import User

    return (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one()


async def _criar_cliente(
    db,
    nome: str,
    responsavel_id: str,
    cpf: str | None = None,
) -> str:
    from app.services.pii_crypto import encrypt, hash_documento, normalizar_documento

    client_id = str(uuid4())
    cpf_n = normalizar_documento(cpf) if cpf else None
    await db.execute(
        text(
            "INSERT INTO clients "
            "(id, tipo, nome, status, responsavel_id, cpf_enc, cpf_hash) "
            "VALUES (:id, 'PF', :nome, 'ativo', :resp, :cpf_enc, :cpf_hash)"
        ),
        {
            "id": client_id,
            "nome": nome,
            "resp": responsavel_id,
            "cpf_enc": encrypt(cpf_n) if cpf_n else None,
            "cpf_hash": hash_documento(cpf_n) if cpf_n else None,
        },
    )
    return client_id


async def _criar_analise(db, user_id: str, potencial_cliente: str) -> str:
    analise_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO raio_x_analises "
            "(id, titulo, potencial_cliente, status, relatorio, revisao_humana, "
            "alertas_conflito, custo_ia, dados_extraidos, prazo_urgente, created_by) "
            "VALUES (:id, 'Análise P0', :nome, 'em_analise', "
            "CAST(:relatorio AS jsonb), '{}'::jsonb, '[]'::jsonb, '{}'::jsonb, "
            "'{}'::jsonb, false, :uid)"
        ),
        {
            "id": analise_id,
            "nome": potencial_cliente,
            "uid": user_id,
            "relatorio": (
                '{"sintese_executiva":"Fato preliminar sujeito a revisão",'
                '"fatos_provas":[{"fato":"Evento alegado","confirmado":false}],'
                '"teses":["Responsabilidade civil a verificar"],'
                '"riscos":["Prova técnica pendente"],'
                '"proximos_passos":["Revisar documentos"],'
                '"documentos_pendentes":["Laudo"],'
                '"prazos_potenciais":[],"fontes":[],"partes":[]}'
            ),
        },
    )
    return analise_id


async def _carregar_analise(db, analise_id: str):
    from sqlalchemy.orm import selectinload
    from app.models.raio_x import RaioXAnalise

    return (
        await db.execute(
            select(RaioXAnalise)
            .options(selectinload(RaioXAnalise.documentos))
            .where(RaioXAnalise.id == analise_id)
        )
    ).scalar_one()


def _payload_existente(client_id: str) -> RaioXConverterRequest:
    return RaioXConverterRequest(
        cliente=ClienteConversao(modo="existente", client_id=client_id),
        caso=CasoConversao(
            titulo="Caso convertido com segurança",
            area="civil",
            prioridade="media",
            case_type="judicial",
        ),
        documento_ids=[],
        transferir_prazos=False,
        transferir_tarefas=False,
        duplicate_confirmed=False,
        conflict_confirmed=False,
        confirmacao="TRANSFORMAR EM CASO DO ESCRITÓRIO",
    )


async def _limpar(db, *, analise_ids=(), case_ids=(), client_ids=(), user_ids=()):
    for analise_id in analise_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(
            text("DELETE FROM audit_logs WHERE entidade = 'raio_x_analises' AND registro_id = :id"),
            {"id": analise_id},
        )
        await db.execute(
            text("DELETE FROM raio_x_documentos WHERE analise_id = :id"),
            {"id": analise_id},
        )
        await db.execute(
            text("DELETE FROM raio_x_analises WHERE id = :id"),
            {"id": analise_id},
        )
    for case_id in case_ids:
        await db.execute(text("DELETE FROM tasks WHERE case_id = :id"), {"id": case_id})
        await db.execute(text("DELETE FROM deadlines WHERE case_id = :id"), {"id": case_id})
        await db.execute(text("DELETE FROM documents WHERE case_id = :id"), {"id": case_id})
        await db.execute(
            text("DELETE FROM case_intelligence_snapshots WHERE case_id = :id"),
            {"id": case_id},
        )
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})
    for client_id in client_ids:
        await db.execute(text("DELETE FROM cases WHERE client_id = :id"), {"id": client_id})
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    for user_id in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": user_id})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_uuid_de_cliente_alheio_nao_pode_ser_vinculado():
    from app.core.database import AsyncSessionLocal
    from app.services.raio_x_service import _resolver_cliente

    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db)
        outro = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Carteira A", dono)
        await db.commit()
        try:
            user_outro = await _carregar_user(db, outro)
            with pytest.raises(HTTPException) as exc:
                await _resolver_cliente(db, _payload_existente(client_id), user_outro)
            assert exc.value.status_code == 404
            assert exc.value.detail == "Cliente não encontrado"
        finally:
            await _limpar(db, client_ids=[client_id], user_ids=[dono, outro])


async def test_deduplicacao_por_cpf_nao_vaza_cliente_alheio():
    from app.core.database import AsyncSessionLocal
    from app.services.raio_x_service import _resolver_cliente

    cpf = "52998224725"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db)
        outro = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Documento Protegido", dono, cpf)
        await db.commit()
        try:
            user_outro = await _carregar_user(db, outro)
            payload = RaioXConverterRequest(
                cliente=ClienteConversao(
                    modo="novo",
                    nome="Tentativa de duplicação",
                    cpf=cpf,
                ),
                caso=CasoConversao(titulo="Caso teste", area="civil"),
                confirmacao="TRANSFORMAR EM CASO DO ESCRITÓRIO",
            )
            with pytest.raises(HTTPException) as exc:
                await _resolver_cliente(db, payload, user_outro)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, client_ids=[client_id], user_ids=[dono, outro])


async def test_preview_redige_cliente_de_outra_carteira():
    from app.core.database import AsyncSessionLocal
    from app.services.raio_x_service import preview_conversao

    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db)
        outro = await _criar_user(db)
        client_id = await _criar_cliente(db, "Pessoa Protegida Exemplo", dono)
        analise_id = await _criar_analise(db, outro, "Pessoa Protegida Exemplo")
        await db.commit()
        try:
            analise = await _carregar_analise(db, analise_id)
            user_outro = await _carregar_user(db, outro)
            preview = await preview_conversao(db, analise, user=user_outro)
            candidatos = preview["clientes_possivelmente_duplicados"]
            assert candidatos
            assert candidatos[0]["protegido"] is True
            assert candidatos[0]["id"] is None
            assert candidatos[0]["nome"] == "Cliente protegido na base do escritório"
            assert "Pessoa Protegida Exemplo" not in str(candidatos)
        finally:
            await _limpar(
                db,
                analise_ids=[analise_id],
                client_ids=[client_id],
                user_ids=[dono, outro],
            )


async def test_conversao_cria_snapshot_raio_x_na_mesma_operacao():
    from app.core.database import AsyncSessionLocal
    from app.models.case_intelligence import CaseIntelligenceSnapshot
    from app.services.raio_x_service import converter_em_caso

    case_id = None
    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Conversão Autorizada", advogado)
        analise_id = await _criar_analise(db, advogado, "Cliente Conversão Autorizada")
        await db.commit()
        try:
            user = await _carregar_user(db, advogado)
            analise = await _carregar_analise(db, analise_id)
            result = await converter_em_caso(
                db,
                analise,
                _payload_existente(client_id),
                user,
            )
            case_id = result["case_id"]
            assert result["snapshot_id"]

            snapshot = (
                await db.execute(
                    select(CaseIntelligenceSnapshot).where(
                        CaseIntelligenceSnapshot.case_id == case_id
                    )
                )
            ).scalar_one()
            assert snapshot.id == result["snapshot_id"]
            assert snapshot.origem == "raio_x"
            assert snapshot.versao == 1
            assert snapshot.congelado is False
            assert snapshot.payload["raio_x_analise_id"] == analise_id
            assert snapshot.payload["revisao_humana_obrigatoria"] is True
        finally:
            await _limpar(
                db,
                analise_ids=[analise_id],
                case_ids=[case_id] if case_id else [],
                client_ids=[client_id],
                user_ids=[advogado],
            )


async def test_conversao_rele_estado_sob_lock_nao_duplica_caso():
    """Achado do security-auditor (F4/#798): antes desta correção,
    converter_em_caso checava `analise.convertido_case_id` no objeto Python
    já carregado pelo chamador — se esse objeto estivesse desatualizado
    (ex.: outra transação converteu/tocou a análise entre o SELECT do router
    e este commit), a checagem de idempotência não via a mudança e criaria um
    SEGUNDO caso. Agora a função rebusca sob `with_for_update` antes de
    checar. Simula a corrida sem depender de dois processos reais: a
    conversão real acontece via uma segunda sessão; o objeto `analise`
    passado à função sob teste é o ORIGINAL, sem essa mudança."""
    from app.core.database import AsyncSessionLocal
    from app.services.raio_x_service import converter_em_caso

    case_id_real = None
    async with AsyncSessionLocal() as db_evento_concorrente, AsyncSessionLocal() as db:
        advogado = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Corrida de Conversão", advogado)
        analise_id = await _criar_analise(db, advogado, "Cliente Corrida de Conversão")
        await db.commit()
        try:
            user = await _carregar_user(db, advogado)
            # Objeto "stale" que o chamador (router) teria em mãos ANTES da
            # corrida — convertido_case_id ainda None neste snapshot.
            analise_stale = await _carregar_analise(db, analise_id)
            assert analise_stale.convertido_case_id is None

            # Outra transação converte a análise "por fora" enquanto o
            # objeto acima já estava carregado em memória.
            user_evento = await _carregar_user(db_evento_concorrente, advogado)
            analise_evento = await _carregar_analise(db_evento_concorrente, analise_id)
            resultado_real = await converter_em_caso(
                db_evento_concorrente, analise_evento, _payload_existente(client_id), user_evento,
            )
            case_id_real = resultado_real["case_id"]
            assert resultado_real["ja_convertido"] is False

            # A chamada com o objeto STALE não pode criar um segundo caso —
            # tem que enxergar, via lock+recheck, que já foi convertida.
            resultado_stale = await converter_em_caso(
                db, analise_stale, _payload_existente(client_id), user,
            )
            assert resultado_stale == {"case_id": case_id_real, "ja_convertido": True}
        finally:
            await _limpar(
                db,
                analise_ids=[analise_id],
                case_ids=[case_id_real] if case_id_real else [],
                client_ids=[client_id],
                user_ids=[advogado],
            )
