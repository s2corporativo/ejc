"""Varredura recursiva do Portal do Cliente — camada 4 (Trilha A, item A3).

Complementa test_portal_idor_matrix_dblevel.py (isolamento por client_id) com
uma pergunta diferente: **mesmo dentro dos dados do PRÓPRIO cliente**, cinco
categorias de campo nunca podem atravessar `/portal/*`, em NENHUM nível do
JSON de resposta — não só nas chaves que o router hoje escolhe devolver:

  1. Estimativa/chance de êxito do caso (case_intel grava em CaseMovimento
     tipo="ia", texto livre "chance≈NN%").
  2. Anotação interna do escritório (CaseMovimento tipo="nota").
  3. Estratégia do caso — tese principal, pontos fortes/fracos, fatos
     internos (Case.tese_principal/pontos_fortes/pontos_fracos/
     descricao_fatos — nunca fizeram parte do dict que os handlers montam,
     mas aqui provamos isso por SEEDING + walk, não por leitura de código).
  4. Proveniência de IA — nome de modelo, id de AILog, resumo gerado por IA
     de um andamento (CaseMovimento.resumo_ia).
  5. Documento não publicado explicitamente ao Portal (Issue #698):
     confidencialidade="normal" sozinho não basta mais — precisa
     `publicado_portal=true` (ato do escritório) OU ser upload do próprio
     cliente; e publicação sobrevive à reclassificação só enquanto a
     classificação continuar permitindo (reavaliada a cada leitura).

Método: em vez de checar só as chaves que sabemos que o router usa, serializa
a resposta como o Portal serializaria de verdade (`jsonable_encoder`, mesma
função que o FastAPI usa) e percorre TODO dict/lista recursivamente — chaves
E valores — procurando o marcador. Prova por negação em profundidade, não
por amostragem de campo.

Padrão idêntico a test_portal_idor_matrix_dblevel.py: handler chamado direto
com AsyncSessionLocal, SQL cru para a massa de teste, RUN_DB_TESTS
obrigatório.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Walker recursivo: prova por negação em QUALQUER profundidade ─────────────


def _achatar(resposta) -> str:
    """Serializa como o FastAPI serializaria de verdade e concatena TODO
    dict/lista recursivamente (chaves e valores) numa única string, para
    checagem de substring. Não amostra campo — percorre tudo."""
    encoded = jsonable_encoder(resposta)
    partes: list[str] = []

    def _andar(node) -> None:
        if isinstance(node, dict):
            for chave, valor in node.items():
                partes.append(str(chave))
                _andar(valor)
        elif isinstance(node, list):
            for item in node:
                _andar(item)
        else:
            partes.append(str(node))

    _andar(encoded)
    return "␟".join(partes)  # separador improvável de colidir com dado real


def _assert_ausente(resposta, marcador: str, onde: str) -> None:
    texto = _achatar(resposta)
    assert marcador not in texto, (
        f"VAZAMENTO em {onde}: marcador {marcador!r} apareceu em algum nível "
        "do JSON de resposta do Portal (varredura recursiva de chaves+valores)."
    )


def _assert_presente(resposta, marcador: str, onde: str) -> None:
    """Controle positivo: sem isto, um handler quebrado que devolve vazio
    faria QUALQUER teste de ausência passar por acidente."""
    texto = _achatar(resposta)
    assert marcador in texto, (
        f"controle positivo falhou em {onde}: {marcador!r} deveria estar "
        "presente — handler pode estar devolvendo vazio/quebrado, o que "
        "mascararia o teste de ausência dos campos bloqueados."
    )


# ── Helpers de massa (mesmo padrão de test_portal_idor_matrix_dblevel.py) ────


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@sweep.local"},
    )
    return cid


async def _criar_portal_user(db, client_id: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, "
             "is_active, client_id) VALUES "
             "(:id, :email, 'x', 'Portal Teste', 'cliente_externo', true, :cid)"),
        {"id": uid, "email": f"portal-{uid[:8]}@sweep.local", "cid": client_id},
    )
    return uid


async def _criar_staff(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, "
             "is_active) VALUES (:id, :email, 'x', 'Staff Teste', :role, true)"),
        {"id": uid, "email": f"staff-{uid[:8]}@sweep.local", "role": role},
    )
    return uid


async def _criar_caso(
    db, client_id: str, titulo: str, *,
    tese: str | None = None, pontos_fortes: str | None = None,
    pontos_fracos: str | None = None, descricao_fatos: str | None = None,
    risco: str | None = None,
) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "tese_principal, pontos_fortes, pontos_fracos, descricao_fatos, "
             "risco) VALUES "
             "(:id, :titulo, 'civil', 'em_instrucao', :cid, "
             " :tese, :pf, :pfr, :fatos, :risco)"),
        {
            "id": case_id, "titulo": titulo, "cid": client_id,
            "tese": tese, "pf": pontos_fortes, "pfr": pontos_fracos,
            "fatos": descricao_fatos, "risco": risco,
        },
    )
    return case_id


async def _criar_movimento(
    db, case_id: str, tipo: str, descricao: str, dias_atras: int, *,
    resumo_ia: str | None = None,
) -> str:
    mov_id = str(uuid4())
    await db.execute(
        text("INSERT INTO case_movimentos (id, case_id, tipo, descricao, "
             "data_evento, resumo_ia) VALUES "
             "(:id, :cid, :tipo, :desc, now() - make_interval(days => :dias), :resumo)"),
        {"id": mov_id, "cid": case_id, "tipo": tipo, "desc": descricao,
         "dias": int(dias_atras), "resumo": resumo_ia},
    )
    return mov_id


async def _criar_documento(
    db, client_id: str, case_id: str | None, titulo: str, confid: str = "normal",
    *, publicado_portal: bool = False, publicado_por: str | None = None,
    uploaded_by: str | None = None,
) -> str:
    doc_id = str(uuid4())
    await db.execute(
        text("INSERT INTO documents (id, titulo, filename, filepath, client_id, "
             "case_id, confidencialidade, publicado_portal, publicado_por, "
             "publicado_em, uploaded_by) VALUES "
             "(:id, :titulo, :fn, :fp, :cid, :case, "
             " CAST(:conf AS docconfidencialidade), :pub, :pubpor, "
             " CASE WHEN :pub THEN now() ELSE NULL END, :upby)"),
        {
            "id": doc_id, "titulo": titulo, "fn": f"{titulo}.pdf",
            "fp": f"2026/08/{doc_id}.pdf", "cid": client_id, "case": case_id,
            "conf": confid, "pub": publicado_portal, "pubpor": publicado_por,
            "upby": uploaded_by,
        },
    )
    return doc_id


async def _criar_fee(db, client_id: str, descricao: str, observacoes: str | None = None) -> str:
    fee_id = str(uuid4())
    await db.execute(
        text("INSERT INTO fees (id, descricao, client_id, valor, data_vencimento, "
             "observacoes) VALUES (:id, :desc, :cid, 1500, '2026-09-10', :obs)"),
        {"id": fee_id, "desc": descricao, "cid": client_id, "obs": observacoes},
    )
    return fee_id


async def _criar_solicitacao(db, client_id: str, case_id: str) -> str:
    sol_id = str(uuid4())
    await db.execute(
        text("INSERT INTO solicitacoes_documentos (id, case_id, client_id) "
             "VALUES (:id, :case, :cid)"),
        {"id": sol_id, "case": case_id, "cid": client_id},
    )
    return sol_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    from sqlalchemy import select
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, client_ids=(), user_ids=()):
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM notifications WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM portal_mensagens WHERE autor_id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(
            text("DELETE FROM portal_mensagens WHERE case_id IN "
                 "(SELECT id FROM cases WHERE client_id = :id)"),
            {"id": cid},
        )
        await db.execute(
            text("DELETE FROM solicitacao_documento_itens WHERE solicitacao_id IN "
                 "(SELECT id FROM solicitacoes_documentos WHERE client_id = :id)"),
            {"id": cid},
        )
        await db.execute(text("DELETE FROM solicitacoes_documentos WHERE client_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM documents WHERE client_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM fees WHERE client_id = :id"), {"id": cid})
        await db.execute(
            text("DELETE FROM case_movimentos WHERE case_id IN "
                 "(SELECT id FROM cases WHERE client_id = :id)"),
            {"id": cid},
        )
        await db.execute(text("DELETE FROM cases WHERE client_id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _respostas_portal(db, user, case_id: str) -> dict:
    """Chama TODOS os endpoints de /portal/* (portal.py + portal_documentos.py)
    para o mesmo cliente e devolve {nome_do_endpoint: resposta_crua}. É a
    "varredura completa" do item 1: nenhum endpoint fica de fora."""
    from app.routers.portal import (
        caso_detalhe, documentos, financeiro, listar_mensagens_portal,
        meus_casos, mensagens_nao_lidas,
    )
    from app.routers.portal_documentos import listar_solicitacoes_portal

    return {
        "meus_casos": await meus_casos(db=db, cu=user),
        "caso_detalhe": await caso_detalhe(case_id=case_id, db=db, cu=user),
        "documentos": await documentos(db=db, cu=user),
        "financeiro": await financeiro(db=db, cu=user),
        "mensagens_nao_lidas": await mensagens_nao_lidas(db=db, cu=user),
        "listar_mensagens_portal": await listar_mensagens_portal(case_id=case_id, db=db, cu=user),
        "listar_solicitacoes_portal": await listar_solicitacoes_portal(db=db, cu=user),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. Estimativa/chance de êxito
# ══════════════════════════════════════════════════════════════════════════════


async def test_bloqueia_chance_de_exito_em_qualquer_endpoint_do_portal():
    """CaseMovimento tipo="ia" com "chance≈NN%" — o mais recente do caso — não
    aparece em NENHUM endpoint do Portal, em nenhum nível do JSON."""
    from app.core.database import AsyncSessionLocal

    tok = uuid4().hex[:6]
    marcador = f"chance≈97%-MARCADOR-{tok}"
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente {tok}")
        uid = await _criar_portal_user(db, cli)
        caso = await _criar_caso(db, cli, f"Caso {tok}")
        oficial = f"Juntada de petição {tok}"
        await _criar_movimento(db, caso, "andamento_oficial", oficial, dias_atras=5)
        await _criar_movimento(
            db, caso, "ia",
            f"IA – Triagem automática {tok}: área≈civil · {marcador} · complexidade=media.",
            dias_atras=1,
        )
        await db.commit()
        try:
            user = await _carregar_user(db, uid)
            respostas = await _respostas_portal(db, user, caso)
            for nome, resp in respostas.items():
                _assert_ausente(resp, marcador, nome)
            # Controle positivo: o andamento oficial precisa continuar visível.
            _assert_presente(respostas["caso_detalhe"], oficial, "caso_detalhe")
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[uid])


# ══════════════════════════════════════════════════════════════════════════════
# 2. Anotação interna do escritório
# ══════════════════════════════════════════════════════════════════════════════


async def test_bloqueia_nota_interna_em_qualquer_endpoint_do_portal():
    """CaseMovimento tipo="nota" com texto de estratégia livre não aparece em
    nenhum endpoint do Portal."""
    from app.core.database import AsyncSessionLocal

    tok = uuid4().hex[:6]
    marcador = f"NOTA-INTERNA-segurar-acordo-ate-a-pericia-{tok}"
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente {tok}")
        uid = await _criar_portal_user(db, cli)
        caso = await _criar_caso(db, cli, f"Caso {tok}")
        oficial = f"Audiência realizada {tok}"
        await _criar_movimento(db, caso, "audiencia", oficial, dias_atras=4)
        await _criar_movimento(db, caso, "nota", marcador, dias_atras=1)
        await db.commit()
        try:
            user = await _carregar_user(db, uid)
            respostas = await _respostas_portal(db, user, caso)
            for nome, resp in respostas.items():
                _assert_ausente(resp, marcador, nome)
            _assert_presente(respostas["meus_casos"], oficial, "meus_casos.ultima_movimentacao")
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[uid])


# ══════════════════════════════════════════════════════════════════════════════
# 3. Estratégia do caso (tese, pontos fortes/fracos, fatos internos)
# ══════════════════════════════════════════════════════════════════════════════


async def test_bloqueia_tese_e_estrategia_em_qualquer_endpoint_do_portal():
    """Case.tese_principal/pontos_fortes/pontos_fracos/descricao_fatos NUNCA
    aparecem no Portal — mesmo estando no MESMO caso que o cliente pode ver."""
    from app.core.database import AsyncSessionLocal

    tok = uuid4().hex[:6]
    m_tese = f"TESE-PRINCIPAL-responsabilidade-objetiva-{tok}"
    m_forte = f"PONTO-FORTE-nexo-causal-provado-{tok}"
    m_fraco = f"PONTO-FRACO-testemunha-fragil-{tok}"
    m_fatos = f"FATOS-INTERNOS-cliente-omitiu-detalhe-{tok}"
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente {tok}")
        uid = await _criar_portal_user(db, cli)
        titulo = f"Caso Estrategia {tok}"
        caso = await _criar_caso(
            db, cli, titulo,
            tese=m_tese, pontos_fortes=m_forte, pontos_fracos=m_fraco,
            descricao_fatos=m_fatos,
        )
        await db.commit()
        try:
            user = await _carregar_user(db, uid)
            respostas = await _respostas_portal(db, user, caso)
            for nome, resp in respostas.items():
                _assert_ausente(resp, m_tese, nome)
                _assert_ausente(resp, m_forte, nome)
                _assert_ausente(resp, m_fraco, nome)
                _assert_ausente(resp, m_fatos, nome)
            _assert_presente(respostas["meus_casos"], titulo, "meus_casos")
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[uid])


# ══════════════════════════════════════════════════════════════════════════════
# 4. Proveniência de IA (modelo, resumo gerado por IA)
# ══════════════════════════════════════════════════════════════════════════════


async def test_bloqueia_provenancia_de_ia_em_qualquer_endpoint_do_portal():
    """CaseMovimento.resumo_ia (andamento traduzido por IA, rascunho) não é
    selecionado por nenhum endpoint — provado por seeding + varredura, não só
    por leitura do SELECT. Mesmo um resumo_ia anexado ao andamento OFICIAL
    visível não deve vazar: só `descricao` é exposta, nunca `resumo_ia`."""
    from app.core.database import AsyncSessionLocal

    tok = uuid4().hex[:6]
    marcador = f"RESUMO-IA-modelo=claude-opus-prompt_id={tok}"
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente {tok}")
        uid = await _criar_portal_user(db, cli)
        caso = await _criar_caso(db, cli, f"Caso {tok}")
        oficial = f"Decisão publicada {tok}"
        await _criar_movimento(
            db, caso, "decisao", oficial, dias_atras=1, resumo_ia=marcador,
        )
        await db.commit()
        try:
            user = await _carregar_user(db, uid)
            respostas = await _respostas_portal(db, user, caso)
            for nome, resp in respostas.items():
                _assert_ausente(resp, marcador, nome)
            _assert_presente(respostas["caso_detalhe"], oficial, "caso_detalhe")
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[uid])


# ══════════════════════════════════════════════════════════════════════════════
# 5. Documento não publicado explicitamente (Issue #698)
# ══════════════════════════════════════════════════════════════════════════════


async def test_bloqueia_documento_normal_nao_publicado_explicitamente():
    """Critérios de aceite da Issue #698, um a um:
      • normal + NUNCA publicado → ausente (por negação);
      • normal + publicado_portal=true → presente;
      • normal + publicado e DEPOIS reclassificado p/ interno → ausente de
        novo, SEM precisar de ato de despublicação (reavaliação a cada leitura);
      • upload do PRÓPRIO cliente (uploaded_by=cu.id), normal, NUNCA
        publicado pelo escritório → presente mesmo assim (ele é o dono)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.portal import documentos

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente {tok}")
        adv = await _criar_staff(db, "advogado")
        uid = await _criar_portal_user(db, cli)
        user = await _carregar_user(db, uid)

        doc_nao_publicado = await _criar_documento(
            db, cli, None, f"nao-publicado-{tok}", "normal",
        )
        doc_publicado = await _criar_documento(
            db, cli, None, f"publicado-{tok}", "normal",
            publicado_portal=True, publicado_por=adv,
        )
        doc_reclassificado = await _criar_documento(
            db, cli, None, f"reclassificado-{tok}", "interno",
            publicado_portal=True, publicado_por=adv,  # publicado no PASSADO
        )
        doc_proprio_cliente = await _criar_documento(
            db, cli, None, f"proprio-cliente-{tok}", "normal",
            uploaded_by=uid,  # sem publicado_portal — auto-visível mesmo assim
        )
        await db.commit()
        try:
            ids = {d["id"] for d in (await documentos(db=db, cu=user))["data"]}
            assert doc_nao_publicado not in ids, "normal sem ato de publicação vazou"
            assert doc_publicado in ids, "normal + publicado deveria aparecer"
            assert doc_reclassificado not in ids, (
                "reclassificado p/ interno depois de publicado deveria sumir "
                "SEM precisar de despublicação explícita"
            )
            assert doc_proprio_cliente in ids, (
                "upload do próprio cliente deveria ficar visível a ele sem "
                "depender de publicação do escritório"
            )
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[uid, adv])


async def test_publicar_no_portal_exige_piso_de_papel_e_grava_autor_e_data():
    """PATCH /documents/{id}/publicacao-portal (endpoint novo, Issue #698):
      • estagiário (abaixo de advogado) não publica documento normal → 403;
      • advogado publica → grava publicado_por/publicado_em + audit log;
      • estagiário com ownership do documento (auxiliar do caso) TAMBÉM não
        DESPUBLICA um documento já publicado — o piso de papel do ato é
        simétrico (mesmo desenho do Data Room `_pode_editar`): revogar
        visibilidade do cliente é decisão do escritório tanto quanto
        concedê-la, não "qualquer um com acesso ao documento";
      • publicar confidencial (nunca aparece no Portal mesmo assim) exige
        piso mais alto (sócio+) — mesma política do Data Room, reutilizada."""
    from app.core.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog
    from app.models.document import Document
    from app.routers.documents import (
        DocumentPublicacaoPortalRequest, publicar_no_portal,
    )
    from fastapi import HTTPException
    from sqlalchemy import select

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente {tok}")
        estagiario = await _criar_staff(db, "estagiario")
        adv = await _criar_staff(db, "advogado")
        # Documento vinculado a um caso do PRÓPRIO advogado (ownership) —
        # senão a checagem de posse (_verificar_acesso_documento) barraria
        # mesmo um advogado antes de chegar ao piso de papel que este teste
        # quer provar.
        caso = await _criar_caso(db, cli, f"Caso publicacao {tok}")
        await db.execute(
            text("UPDATE cases SET advogado_responsavel_id = :adv WHERE id = :cid"),
            {"adv": adv, "cid": caso},
        )
        doc_id = await _criar_documento(db, cli, caso, f"a-publicar-{tok}", "normal")
        await db.commit()
        try:
            user_estagiario = await _carregar_user(db, estagiario)
            user_adv = await _carregar_user(db, adv)

            # Piso de papel: estagiário não publica.
            with pytest.raises(HTTPException) as exc:
                await publicar_no_portal(
                    doc_id=doc_id,
                    req=DocumentPublicacaoPortalRequest(publicado=True),
                    db=db, cu=user_estagiario,
                )
            assert exc.value.status_code == 403

            # Advogado publica: grava autor + data + audit log.
            out = await publicar_no_portal(
                doc_id=doc_id,
                req=DocumentPublicacaoPortalRequest(publicado=True),
                db=db, cu=user_adv,
            )
            assert out["publicado_portal"] is True
            assert out["publicado_por"] == adv
            assert out["publicado_em"] is not None

            log = (await db.execute(
                select(AuditLog).where(
                    AuditLog.registro_id == doc_id, AuditLog.acao == "PUBLISH_PORTAL",
                )
            )).scalar_one_or_none()
            assert log is not None, "ato de publicar precisa gravar audit log"

            # Piso simétrico: estagiário com OWNERSHIP do doc (auxiliar do
            # caso, passa o gate de posse) ainda assim não despublica —
            # o piso de papel do ato vale para as duas direções.
            await db.execute(
                text(
                    "UPDATE cases SET advogado_auxiliar_id = :est WHERE id = :cid"
                ),
                {"est": estagiario, "cid": caso},
            )
            await db.commit()
            with pytest.raises(HTTPException) as exc_desp:
                await publicar_no_portal(
                    doc_id=doc_id,
                    req=DocumentPublicacaoPortalRequest(publicado=False),
                    db=db, cu=user_estagiario,
                )
            assert exc_desp.value.status_code == 403
            ainda_publicado = (await db.execute(
                select(Document.publicado_portal).where(Document.id == doc_id)
            )).scalar_one()
            assert ainda_publicado is True, (
                "estagiário sem piso não pode ter conseguido despublicar"
            )

            # Despublicar: limpa autor/data e grava audit log de despublicação.
            out2 = await publicar_no_portal(
                doc_id=doc_id,
                req=DocumentPublicacaoPortalRequest(publicado=False),
                db=db, cu=user_adv,
            )
            assert out2["publicado_portal"] is False
            assert out2["publicado_por"] is None
            log2 = (await db.execute(
                select(AuditLog).where(
                    AuditLog.registro_id == doc_id, AuditLog.acao == "UNPUBLISH_PORTAL",
                )
            )).scalar_one_or_none()
            assert log2 is not None, "ato de despublicar precisa gravar audit log"
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[estagiario, adv])
