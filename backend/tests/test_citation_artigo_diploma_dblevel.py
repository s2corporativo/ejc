"""P0 — verificação determinística de artigo × diploma com Postgres real."""
from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _isolar_pool_por_event_loop():
    from app.core.database import engine

    await engine.dispose(close=False)
    yield
    await engine.dispose(close=False)


async def _inserir_diploma(
    db,
    *,
    chave: str,
    titulo: str,
    conteudo: str,
    vigente: bool = True,
    versao: int = 1,
    legal_status: str | None = "vigente",
    legal_status_verificado_em: str | None = "2026-08-01T10:00:00Z",
) -> str:
    """Diploma como a ingestão o grava HOJE (P0.1): legislação carrega
    `extra.legal_status` COM proveniência positiva completa (origem e data de
    verificação, SEM carimbo de inferência). `legal_status=None` reproduz o
    acervo legado, ainda não reingerido — que o gate de vigência exclui.
    `legal_status_verificado_em=None` reproduz inferência (sem proveniência
    completa) — que o gate estrito também rejeita."""
    doc_id = str(uuid4())
    extra = {"rag_status": "aprovado", "confidence_level": "alta"}
    if legal_status is not None:
        extra["legal_status"] = legal_status
        extra["legal_status_origem"] = "planalto:texto_compilado"
        if legal_status_verificado_em is not None:
            extra["legal_status_verificado_em"] = legal_status_verificado_em
    await db.execute(
        text(
            """
            INSERT INTO knowledge_docs (
                id, titulo, categoria, chave_origem, status_indexacao,
                versao, vigente, revisado, extra, base_rag
            ) VALUES (
                :id, :titulo, 'legislacao', :chave, 'indexado',
                :versao, :vigente, true,
                CAST(:extra AS jsonb), 'publica'
            )
            """
        ),
        {
            "id": doc_id,
            "titulo": titulo,
            "chave": chave,
            "versao": versao,
            "vigente": vigente,
            "extra": json.dumps(extra),
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo)
            VALUES (:id, :doc_id, 0, :conteudo)
            """
        ),
        {"id": str(uuid4()), "doc_id": doc_id, "conteudo": conteudo},
    )
    return doc_id


async def _limpar(db, ids: list[str]) -> None:
    if ids:
        await db.execute(
            text("DELETE FROM knowledge_docs WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        await db.commit()


async def _verificar(db, texto_citacao: str) -> dict:
    from app.services.citation_check import verificar_citacoes

    relatorio = await verificar_citacoes(db, texto_citacao)
    assert relatorio["total"] == 1
    return relatorio["citacoes"][0]


@pytest.mark.parametrize(
    (
        "texto_citacao",
        "numero",
        "chave_correta",
        "titulo_correto",
        "chave_errada",
        "titulo_errado",
    ),
    [
        (
            "Tutela de urgência conforme o art. 300 do CPC.",
            "300",
            "planalto:cpc",
            "Código de Processo Civil (Lei 13.105/2015)",
            "planalto:cp",
            "Código Penal (DL 2.848/1940)",
        ),
        (
            "Garantia fundamental prevista no art. 5º da CF.",
            "5",
            "planalto:cf88",
            "Constituição Federal de 1988",
            "planalto:cc",
            "Código Civil (Lei 10.406/2002)",
        ),
        (
            "Direito básico do consumidor previsto no art. 6º do CDC.",
            "6",
            "planalto:cdc",
            "Código de Defesa do Consumidor (Lei 8.078/1990)",
            "planalto:ctn",
            "Código Tributário Nacional (Lei 5.172/1966)",
        ),
        (
            "Responsabilidade civil fundada no art. 927 do CC.",
            "927",
            "planalto:cc",
            "Código Civil (Lei 10.406/2002)",
            "planalto:cpc",
            "Código de Processo Civil (Lei 13.105/2015)",
        ),
    ],
)
async def test_artigo_so_confirma_no_diploma_citado_e_expoe_fonte(
    texto_citacao,
    numero,
    chave_correta,
    titulo_correto,
    chave_errada,
    titulo_errado,
):
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            ids.append(
                await _inserir_diploma(
                    db,
                    chave=chave_errada,
                    titulo=titulo_errado,
                    conteudo=f"Art. {numero}. Dispositivo homônimo do diploma errado.",
                )
            )
            id_correto = await _inserir_diploma(
                db,
                chave=chave_correta,
                titulo=titulo_correto,
                conteudo=f"Art. {numero}. Texto vigente do diploma correto.",
            )
            ids.append(id_correto)
            await db.commit()

            citacao = await _verificar(db, texto_citacao)

            assert citacao["status"] == "verificada"
            assert citacao["encontrada"] is True
            assert citacao["fonte_chave_origem"] == chave_correta
            assert citacao["fonte_titulo"] == titulo_correto
            assert citacao["fonte_doc_id"] == id_correto
            assert citacao["fonte_versao"] == 1
            assert citacao["fonte_vigente"] is True
        finally:
            await _limpar(db, ids)


async def test_artigo_existente_apenas_em_outro_diploma_nao_recebe_selo_positivo():
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:cp",
                    titulo="Código Penal (DL 2.848/1940)",
                    conteudo="Art. 300. Dispositivo existente somente no diploma errado.",
                )
            )
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:cpc",
                    titulo="Código de Processo Civil (Lei 13.105/2015)",
                    conteudo="Art. 301. Outro dispositivo, sem o artigo citado.",
                )
            )
            await db.commit()

            citacao = await _verificar(
                db,
                "Tutela de urgência conforme o art. 300 do CPC.",
            )
            assert citacao["status"] != "verificada"
            assert citacao["encontrada"] is False
            assert citacao["fonte_chave_origem"] is None
        finally:
            await _limpar(db, ids)


@pytest.mark.parametrize(
    "abreviacao",
    ["Lei nº 8.078/90", "Lei n.º 8.078/90", "Lei n.o 8.078/90", "Lei n° 8.078/90"],
)
async def test_lei_por_numero_normalizado_aceita_abreviacoes_compostas(abreviacao):
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:l18078",
                    titulo="Lei Experimental (Lei 18.078/2020)",
                    conteudo="Art. 6º. Diploma de número apenas parecido.",
                )
            )
            id_cdc = await _inserir_diploma(
                db,
                chave="planalto:cdc",
                titulo="Código de Defesa do Consumidor (Lei 8.078/1990)",
                conteudo="Art. 6º. Direitos básicos do consumidor.",
            )
            ids.append(id_cdc)
            await db.commit()

            citacao = await _verificar(
                db,
                f"Aplicação do art. 6º da {abreviacao}.",
            )
            assert citacao["status"] == "verificada"
            assert citacao["fonte_chave_origem"] == "planalto:cdc"
            assert citacao["fonte_doc_id"] == id_cdc
            assert "18.078" not in citacao["fonte_titulo"]
        finally:
            await _limpar(db, ids)


async def test_legislacao_sem_vigencia_declarada_nao_confirma_a_citacao(monkeypatch):
    """Issue #636, no nível do GATE DE CITAÇÃO: o artigo existe, está no diploma
    citado e a curadoria o aprovou — mas ninguém conferiu a vigência da norma.
    Com RAG_EXIGIR_VIGENCIA_VERIFICADA ligada (default), a citação NÃO recebe o
    selo 'verificada'; desligada, volta a receber. É o mesmo documento e o mesmo
    texto nos dois casos: só a flag muda."""
    from app.core.database import AsyncSessionLocal
    from app.services import ai_service

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            id_cpc = await _inserir_diploma(
                db,
                chave="planalto:cpc",
                titulo="Código de Processo Civil (Lei 13.105/2015)",
                conteudo="Art. 300. Texto do diploma ainda não reingerido.",
                legal_status=None,
            )
            ids.append(id_cpc)
            await db.commit()
            texto = "Tutela de urgência conforme o art. 300 do CPC."

            monkeypatch.setattr(
                ai_service.settings, "RAG_EXIGIR_VIGENCIA_VERIFICADA", True)
            estrita = await _verificar(db, texto)
            assert estrita["status"] == "identificada", (
                "legislação com vigência não conferida NÃO pode receber selo "
                "de citação verificada")
            assert estrita["encontrada"] is False
            # O texto atual pode ser identificado sem receber selo verde: a
            # fonte fica rastreável, mas o gate jurídico continua fail-closed.
            assert estrita["vigencia_pendente"] is True
            assert estrita["fonte_chave_origem"] == "planalto:cpc"
            assert estrita["fonte_doc_id"] == id_cpc
            assert estrita["fonte_vigente"] is True

            monkeypatch.setattr(
                ai_service.settings, "RAG_EXIGIR_VIGENCIA_VERIFICADA", False)
            frouxa = await _verificar(db, texto)
            assert frouxa["status"] == "verificada", (
                "com a flag desligada o acervo não reingerido deve voltar a "
                "confirmar a citação")
            assert frouxa["fonte_doc_id"] == id_cpc
        finally:
            await _limpar(db, ids)


async def test_norma_revogada_nunca_confirma_a_citacao(monkeypatch):
    """A exclusão do REVOGADO não tem flag: mesmo com
    RAG_EXIGIR_VIGENCIA_VERIFICADA desligada, artigo de norma revogada não vira
    fundamentação confirmada."""
    from app.core.database import AsyncSessionLocal
    from app.services import ai_service

    monkeypatch.setattr(
        ai_service.settings, "RAG_EXIGIR_VIGENCIA_VERIFICADA", False)
    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:cpc",
                    titulo="Código de Processo Civil (Lei 13.105/2015)",
                    conteudo="Art. 300. Dispositivo de diploma revogado.",
                    legal_status="revogada",
                )
            )
            await db.commit()

            citacao = await _verificar(
                db, "Tutela de urgência conforme o art. 300 do CPC.")
            assert citacao["status"] != "verificada"
            assert citacao["encontrada"] is False
            assert citacao["fonte_chave_origem"] is None
        finally:
            await _limpar(db, ids)


async def test_versao_superada_mantem_o_mesmo_recorte_de_diploma():
    """A versão histórica entra SEM `legal_status` de propósito: a governança
    classifica toda versão não vigente como 'historica' (situação declarada) e
    o gate de vigência precisa espelhar esse ramo. Se o espelho SQL voltar a
    ignorar `kd.vigente`, `_artigo_superado` perde o hit e o veredito cai para
    'identificada' — o aviso de desatualização some sem ninguém perceber."""
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            id_cc = await _inserir_diploma(
                db,
                chave="planalto:cc",
                titulo="Código Civil (Lei 10.406/2002)",
                conteudo="Art. 927. Versão histórica do dispositivo.",
                vigente=False,
                versao=2,
                legal_status=None,
            )
            ids.append(id_cc)
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:cpc",
                    titulo="Código de Processo Civil (Lei 13.105/2015)",
                    conteudo="Art. 927. Dispositivo vigente de outro diploma.",
                )
            )
            await db.commit()

            citacao = await _verificar(
                db,
                "Responsabilidade civil fundada no art. 927 do CC.",
            )
            assert citacao["status"] == "possivelmente_desatualizada"
            assert citacao["encontrada"] is False
            assert citacao["fonte_chave_origem"] == "planalto:cc"
            assert citacao["fonte_doc_id"] == id_cc
            assert citacao["fonte_versao"] == 2
            assert citacao["fonte_vigente"] is False
        finally:
            await _limpar(db, ids)


async def test_diploma_vigente_sem_data_verificacao_nao_e_recuperado_pelo_gate_estrito():
    """P0.1: legislação vigente='vigente' SEM legal_status_verificado_em (apenas
    inferido) NÃO passa pelo gate estrito de vigência. O diploma existe no
    banco e citation_check poderia achá-lo, mas o filtro RAG o exclui."""
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            # Diploma vigente COM legal_status mas SEM data de verificação
            # (só tem carimbo de inferência) — gate estrito deve rejeitar
            id_inferido = await _inserir_diploma(
                db,
                chave="planalto:cdc",
                titulo="Código de Defesa do Consumidor (Lei 8.078/1990)",
                conteudo="Art. 6. Direitos básicos do consumidor (versão inferida).",
                legal_status="vigente",
                legal_status_verificado_em=None,  # SEM proveniência completa
            )
            ids.append(id_inferido)
            # Adicionar o campo de inferência manualmente via UPDATE
            await db.execute(
                text(
                    "UPDATE knowledge_docs SET extra = extra || "
                    "CAST(:inf AS jsonb) WHERE id = :id"
                ),
                {"id": id_inferido, "inf": json.dumps({"legal_status_inferido_em": "2026-08-01T10:00:00Z"})}
            )
            await db.commit()

            # Tentativa de verificação de citação: como o gate estrito está
            # ligado e o documento não tem proveniência completa, NÃO deve
            # ser encontrado pelo RAG/busca de citações
            citacao = await _verificar(
                db,
                "Direito básico do consumidor previsto no art. 6º do CDC.",
            )
            # Como o filtro RAG o exclui, a citação NÃO é verificada
            assert citacao["status"] != "verificada", (
                "diploma sem data de verificação passou pelo gate estrito")
            assert citacao["encontrada"] is False
        finally:
            await _limpar(db, ids)


async def test_texto_atual_com_vigencia_pendente_nao_e_rotulado_como_superado():
    """A versão atual pode estar presente e aprovada, mas ainda sem curadoria de
    vigência. O gate continua negando selo ``verificada``; o diagnóstico, porém,
    não pode mentir dizendo que o artigo existe APENAS em versão histórica.
    """
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            atual = await _inserir_diploma(
                db,
                chave="planalto:cdc",
                titulo="Código de Defesa do Consumidor (Lei 8.078/1990)",
                conteudo="Art. 26. Texto atual ingerido, vigência ainda pendente.",
                vigente=True,
                versao=3,
                legal_status="vigencia_nao_verificada",
                legal_status_verificado_em=None,
            )
            ids.append(atual)
            # Reproduz o carimbo fail-closed do ingestor Planalto.
            await db.execute(
                text(
                    "UPDATE knowledge_docs SET extra = extra || "
                    "CAST(:extra AS jsonb) WHERE id = :id"
                ),
                {
                    "id": atual,
                    "extra": json.dumps({
                        "legal_status_origem": "planalto:texto_compilado",
                        "legal_status_inferido_em": "2026-09-13T03:00:00Z",
                    }),
                },
            )
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:cdc",
                    titulo="Código de Defesa do Consumidor (Lei 8.078/1990)",
                    conteudo="Art. 26. Redação histórica do dispositivo.",
                    vigente=False,
                    versao=2,
                    legal_status=None,
                )
            )
            await db.commit()

            citacao = await _verificar(
                db,
                "Prazo previsto no art. 26 do CDC.",
            )

            assert citacao["status"] == "identificada"
            assert citacao["encontrada"] is False
            assert citacao["vigencia_pendente"] is True
            assert citacao["fonte_doc_id"] == atual
            assert citacao["fonte_vigente"] is True
            assert citacao["fonte_chave_origem"] == "planalto:cdc"
            assert "versão atual" in citacao["aviso"]
            assert "SUPERADA" not in citacao["aviso"]
        finally:
            await _limpar(db, ids)
