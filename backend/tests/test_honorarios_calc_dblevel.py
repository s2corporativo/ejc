"""T-P1-2 — o cálculo de honorários, exercitado contra valores.

`docs/auditoria-ejc/14-testes.md`, T-P1-2: "honorários/financeiro sem teste de
cálculo nem de persistência". É dinheiro, e o precedente é fresco — o teste que
faltava no `pix.py` achou um BR Code corrompido em produção.

`honorarios_calc.py` é determinístico e curto (106 linhas), o que engana: o
`teto-etico` é um alerta ÉTICO (EOAB, quota litis — honorários não podem
consumir mais da metade do proveito do cliente), e um alerta que erra para menos
**deixa de disparar exatamente quando deveria**. Silêncio e conformidade têm a
mesma aparência.

Dois defeitos encontrados ao escrever este arquivo, corrigidos no mesmo commit:

1. **honorário MISTO só contava a parte fixa.** O `elif` somava `percentual_exito`
   apenas quando `valor` era nulo — mas `misto` é, por definição, fixo + êxito, e
   o model permite os dois campos. Um contrato de R$ 5.000 + 30% sobre R$ 100.000
   entrava no cálculo como R$ 5.000: o teto era subestimado em R$ 30.000, e o
   alerta ficava mudo no caso mais propenso a estourá-lo.
2. **sucumbência lançada era contada DUAS vezes.** Um `Fee` do tipo `sucumbencia`
   entrava em `contratual`, e depois a estimativa `proveito × 15%` era somada por
   cima. O alerta disparava em caso conforme.

Os dois erram em direções opostas, o que é pior do que errar sempre para o mesmo
lado: não há como corrigir "no olho" um número que ora sobra, ora falta.

Contra Postgres real (RUN_DB_TESTS=1) — o cálculo lê `Fee` do banco.
"""
from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _criar_socio(db):
    """`socio` é gestão: passa no gate de ownership de qualquer caso."""
    from app.models.user import User

    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Socio Teste Honorarios', 'socio', true)"),
        {"id": uid, "email": f"hon-{uid[:8]}@teste.local"},
    )
    await db.commit()
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _criar_caso(db, valor_causa) -> tuple[str, str]:
    """Devolve (case_id, client_id)."""
    cid, client_id = str(uuid4()), str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, status) "
             "VALUES (:id, 'PF', 'Cliente Honorarios', 'ativo')"),
        {"id": client_id},
    )
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, valor_causa) "
             "VALUES (:id, 'Caso Honorarios', 'civil', 'aberto', :cli, :vc)"),
        {"id": cid, "cli": client_id, "vc": valor_causa},
    )
    await db.commit()
    return cid, client_id


async def _criar_fee(db, case_id, client_id, *, tipo, valor=None,
                     percentual=None, status="pendente") -> str:
    fid = str(uuid4())
    await db.execute(
        text("INSERT INTO fees (id, case_id, client_id, tipo, valor, "
             " percentual_exito, status, descricao) "
             "VALUES (:id, :caso, :cli, :tipo, :valor, :pct, :st, 'teste')"),
        {"id": fid, "caso": case_id, "cli": client_id, "tipo": tipo,
         "valor": valor, "pct": percentual, "st": status},
    )
    await db.commit()
    return fid


async def _limpar(db, case_id=None, client_id=None, user_id=None):
    if case_id:
        await db.execute(text("DELETE FROM fees WHERE case_id = :id"), {"id": case_id})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})
    if client_id:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    if user_id:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": user_id})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.commit()


# ── Provisionamento de sucumbência (art. 85 §2º CPC) ─────────────────────────

async def test_provisionamento_aplica_a_faixa_de_10_a_20_por_cento():
    """A faixa é LEI, não parâmetro: art. 85 §2º CPC fixa 10%–20%. O provável é
    o meio da faixa. Números conferidos à mão, não derivados do próprio código."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import provisionamento

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        try:
            r = await provisionamento(caso, None, db, cu)
            assert r["ok"] is True
            assert r["base"] == 100000.0
            assert r["sucumbencia_min"] == 10000.00
            assert r["sucumbencia_provavel"] == 15000.00
            assert r["sucumbencia_max"] == 20000.00
            assert "85" in r["fundamento"]
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_condenacao_informada_substitui_o_valor_da_causa():
    """O valor da causa é a estimativa inicial; a condenação é o número real. A
    provisão tem de seguir o segundo quando ele existe."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import provisionamento

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        try:
            r = await provisionamento(caso, 250000.0, db, cu)
            assert r["base"] == 250000.0
            assert r["sucumbencia_provavel"] == 37500.00
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_arredondamento_e_ao_centavo_e_nao_ao_real():
    """R$ 33.333,33 × 15% = R$ 4.999,9995. Truncar ao real perderia centavos em
    toda provisão; o `quantize(_CENT)` arredonda ao centavo."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import provisionamento

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("33333.33"))
        try:
            r = await provisionamento(caso, None, db, cu)
            assert r["sucumbencia_provavel"] == 5000.00   # 4999.9995 → 5000.00
            assert r["sucumbencia_min"] == 3333.33        # 3333.333  → 3333.33
        finally:
            await _limpar(db, caso, cli, cu.id)


@pytest.mark.parametrize("valor_causa", [Decimal("0.00"), None])
async def test_sem_base_nao_inventa_numero(valor_causa):
    """Caso sem valor da causa devolve aviso, não zero — um provisionamento de
    R$ 0,00 pareceria calculado e não é."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import provisionamento

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, valor_causa)
        try:
            r = await provisionamento(caso, None, db, cu)
            assert r["ok"] is False
            assert "condenacao" in r["aviso"]
        finally:
            await _limpar(db, caso, cli, cu.id)


# ── Teto ético (EOAB / quota litis) ──────────────────────────────────────────

async def test_teto_etico_nao_alerta_dentro_do_parametro():
    """Honorário fixo modesto: 10 mil + 15 mil de sucumbência = 25% de 100 mil."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="fixo", valor=Decimal("10000.00"))
        try:
            r = await teto_etico(caso, db, cu)
            assert r["honorarios_contratuais"] == 10000.00
            assert r["sucumbencia_estimada"] == 15000.00
            assert r["total_honorarios"] == 25000.00
            assert r["percentual_sobre_proveito"] == 25.0
            assert r["alerta_teto"] is False
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_teto_etico_alerta_acima_de_50_por_cento():
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="fixo", valor=Decimal("40000.00"))
        try:
            r = await teto_etico(caso, db, cu)
            assert r["total_honorarios"] == 55000.00     # 40k + 15k sucumbência
            assert r["alerta_teto"] is True
            assert "50%" in r["mensagem"]
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_honorario_de_exito_entra_pelo_percentual():
    """Contrato só de êxito: 30% sobre 100 mil = 30 mil, mais 15 mil de
    sucumbência = 45%. Ainda dentro do parâmetro."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="exito", percentual=Decimal("30.00"))
        try:
            r = await teto_etico(caso, db, cu)
            assert r["honorarios_contratuais"] == 30000.00
            assert r["alerta_teto"] is False
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_honorario_MISTO_soma_a_parte_fixa_E_o_percentual():
    """DEFEITO 1 — o `elif` fazia o misto contar SÓ a parte fixa.

    `misto` é, por definição, fixo + êxito, e o model permite os dois campos
    preenchidos. Um contrato de R$ 5.000 + 30% sobre R$ 100.000 vale R$ 35.000
    para o escritório; entrava no cálculo como R$ 5.000.

    Com o total real (5k + 30k + 15k de sucumbência = 50k), o percentual é
    exatamente 50% — no limite. Com o defeito, dava 20% e o número exibido ao
    advogado subestimava a própria remuneração em R$ 30.000.
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="misto",
                         valor=Decimal("5000.00"), percentual=Decimal("30.00"))
        try:
            r = await teto_etico(caso, db, cu)
            assert r["honorarios_contratuais"] == 35000.00, (
                "honorário misto contou só a parte fixa — o percentual de êxito sumiu"
            )
            assert r["total_honorarios"] == 50000.00
            assert r["percentual_sobre_proveito"] == 50.0
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_misto_com_percentual_alto_dispara_o_alerta():
    """A consequência do defeito 1: é justamente o contrato misto com êxito
    gordo que estoura o teto — e era justamente ele que o alerta não via."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="misto",
                         valor=Decimal("10000.00"), percentual=Decimal("40.00"))
        try:
            r = await teto_etico(caso, db, cu)   # 10k + 40k + 15k = 65k = 65%
            assert r["total_honorarios"] == 65000.00
            assert r["alerta_teto"] is True, (
                "o alerta ético ficou MUDO num contrato que consome 65% do "
                "proveito do cliente"
            )
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_sucumbencia_ja_lancada_nao_e_contada_duas_vezes():
    """DEFEITO 2 — sucumbência lançada + sucumbência estimada, somadas.

    Um `Fee` do tipo `sucumbencia` entrava em `contratual`; depois a estimativa
    `proveito × 15%` era somada por cima. O mesmo dinheiro contava duas vezes, e
    o alerta ético disparava em caso conforme — o erro oposto ao defeito 1.

    Quando há sucumbência lançada, ela SUBSTITUI a estimativa: o valor real é
    melhor que a projeção.
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="fixo", valor=Decimal("20000.00"))
        await _criar_fee(db, caso, cli, tipo="sucumbencia", valor=Decimal("18000.00"))
        try:
            r = await teto_etico(caso, db, cu)
            assert r["honorarios_contratuais"] == 20000.00, (
                "a sucumbência lançada foi somada aos honorários CONTRATUAIS"
            )
            assert r["sucumbencia_estimada"] == 18000.00, (
                "a sucumbência real deveria substituir a estimativa de 15%"
            )
            assert r["total_honorarios"] == 38000.00   # e não 53.000
            assert r["alerta_teto"] is False
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_reembolso_de_despesas_nao_e_honorario():
    """`custas_despesas` é reembolso — dinheiro que o escritório adiantou e
    recebe de volta. Contá-lo como honorário inflaria o teto ético."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="fixo", valor=Decimal("10000.00"))
        await _criar_fee(db, caso, cli, tipo="custas_despesas",
                         valor=Decimal("30000.00"))
        try:
            r = await teto_etico(caso, db, cu)
            assert r["honorarios_contratuais"] == 10000.00
            assert r["alerta_teto"] is False
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_honorario_cancelado_sai_do_calculo():
    """Honorário cancelado não é devido — e um cancelado somando ao teto faria
    o alerta acusar um contrato que não existe mais."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="fixo", valor=Decimal("10000.00"))
        await _criar_fee(db, caso, cli, tipo="fixo", valor=Decimal("45000.00"),
                         status="cancelado")
        try:
            r = await teto_etico(caso, db, cu)
            assert r["honorarios_contratuais"] == 10000.00
            assert r["alerta_teto"] is False
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_caso_sem_proveito_nao_divide_por_zero():
    """Sem valor da causa não há percentual a calcular — e não pode estourar."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, None)
        await _criar_fee(db, caso, cli, tipo="fixo", valor=Decimal("10000.00"))
        try:
            r = await teto_etico(caso, db, cu)
            assert r["percentual_sobre_proveito"] is None
            assert r["alerta_teto"] is False
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_resposta_declara_se_a_sucumbencia_e_real_ou_projetada():
    """Um valor apurado e uma projeção de 15% não podem sair com a mesma cara.

    `sucumbencia_fonte` existe para a interface poder dizer ao advogado qual dos
    dois ele está lendo — a diferença muda a decisão de aceitar acordo.
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        try:
            assert (await teto_etico(caso, db, cu))["sucumbencia_fonte"] == "estimada"

            await _criar_fee(db, caso, cli, tipo="sucumbencia",
                             valor=Decimal("22000.00"))
            r = await teto_etico(caso, db, cu)
            assert r["sucumbencia_fonte"] == "lancada"
            assert r["sucumbencia_estimada"] == 22000.00
        finally:
            await _limpar(db, caso, cli, cu.id)


async def test_exito_ja_apurado_nao_conta_percentual_por_cima():
    """Guarda contra o erro OPOSTO ao do misto: num honorário de êxito com valor
    já fechado, o percentual não pode somar de novo — o valor É o percentual
    apurado. Sem este teste, "somar os dois campos" viraria regra geral."""
    from app.core.database import AsyncSessionLocal
    from app.routers.honorarios_calc import teto_etico

    async with AsyncSessionLocal() as db:
        cu = await _criar_socio(db)
        caso, cli = await _criar_caso(db, Decimal("100000.00"))
        await _criar_fee(db, caso, cli, tipo="exito",
                         valor=Decimal("28000.00"), percentual=Decimal("30.00"))
        try:
            r = await teto_etico(caso, db, cu)
            assert r["honorarios_contratuais"] == 28000.00, (
                "o percentual foi somado por cima de um êxito já apurado"
            )
        finally:
            await _limpar(db, caso, cli, cu.id)
