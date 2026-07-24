from __future__ import annotations

from app.schemas.document_intake import (
    ClienteExtraido,
    DocumentoIntakeResult,
    ParteExtraida,
    PedidoExtraido,
    PrazoExtraido,
    RiscoExtraido,
    TeseSugerida,
)
from app.schemas.leitor_autos import DocumentoAutosEntrada, FonteDocumentoAutos
from app.services.leitor_autos_service import agregar_autos


def _entrada(
    *,
    ordem: int,
    documento_id: str,
    nome: str,
    data: str,
    intake: DocumentoIntakeResult,
    status: str = "confirmada",
    parcial: bool = False,
):
    return DocumentoAutosEntrada(
        ordem=ordem,
        fonte=FonteDocumentoAutos(
            documento_id=documento_id,
            nome_arquivo=nome,
            pagina=1,
            status_fonte=status,
            data_documento=data,
        ),
        intake=intake,
        parcial=parcial,
    )


def test_agrega_partes_pedidos_e_fontes_sem_duplicar():
    doc1 = _entrada(
        ordem=1,
        documento_id="doc-1",
        nome="inicial.pdf",
        data="01/03/2026",
        intake=DocumentoIntakeResult(
            tipo_documento="peticao_inicial",
            partes=[ParteExtraida(nome="Maria da Silva", papel="autora")],
            pedidos=[PedidoExtraido(descricao="Condenação ao pagamento")],
            resumo_fatos="Cobrança contratual.",
        ),
    )
    doc2 = _entrada(
        ordem=2,
        documento_id="doc-2",
        nome="contestacao.pdf",
        data="10/03/2026",
        intake=DocumentoIntakeResult(
            tipo_documento="contestacao",
            partes=[ParteExtraida(nome="Maria da Silva", papel="autora")],
            pedidos=[PedidoExtraido(descricao="Condenação ao pagamento")],
            resumo_fatos="Defesa impugna a cobrança.",
        ),
    )

    resultado = agregar_autos([doc2, doc1])

    assert [item.documento_id for item in resultado.indice] == ["doc-1", "doc-2"]
    assert len(resultado.partes) == 1
    assert resultado.partes[0].nome == "Maria da Silva"
    assert {f.documento_id for f in resultado.partes[0].fontes} == {
        "doc-1",
        "doc-2",
    }
    assert len(resultado.pedidos) == 1
    assert {f.documento_id for f in resultado.pedidos[0].fontes} == {
        "doc-1",
        "doc-2",
    }


def test_cronologia_usa_somente_datas_parseaveis_e_prazos_explicitos():
    entrada = _entrada(
        ordem=1,
        documento_id="doc-1",
        nome="intimacao.pdf",
        data="15/04/2026",
        intake=DocumentoIntakeResult(
            tipo_documento="intimacao",
            prazos=[
                PrazoExtraido(
                    tipo="contestacao",
                    termo_final="30/04/2026",
                    fatal=True,
                    base_legal="CPC, art. 335",
                ),
                PrazoExtraido(tipo="prazo sem data", termo_final=None),
            ],
            resumo_fatos="Intimação para apresentar defesa.",
        ),
    )

    resultado = agregar_autos([entrada])

    assert len(resultado.prazos) == 1
    assert resultado.prazos[0].termo_final == "30/04/2026"
    assert [evento.tipo for evento in resultado.cronologia] == [
        "documento",
        "prazo_explicito",
    ]
    assert resultado.estatisticas.prazos_explicitos == 1


def test_cliente_provavel_e_riscos_teses_sao_rastreaveis():
    entrada = _entrada(
        ordem=1,
        documento_id="doc-1",
        nome="parecer.pdf",
        data="2026-05-01",
        intake=DocumentoIntakeResult(
            tipo_documento="parecer",
            cliente=ClienteExtraido(nome="Empresa Alfa"),
            riscos=[RiscoExtraido(descricao="Prescrição a conferir", impacto="alto")],
            teses=[TeseSugerida(titulo="Inexistência do débito")],
            resumo_fatos="Consulta sobre cobrança.",
        ),
    )

    resultado = agregar_autos([entrada])

    assert resultado.partes[0].papeis == ["provavel_cliente"]
    assert resultado.riscos[0].fontes[0].documento_id == "doc-1"
    assert resultado.teses[0].fontes[0].documento_id == "doc-1"


def test_analise_parcial_e_fonte_pendente_geram_alertas_e_lacunas():
    entrada = _entrada(
        ordem=1,
        documento_id="doc-1",
        nome="scan.pdf",
        data="data ilegivel",
        status="pendente_conferencia",
        parcial=True,
        intake=DocumentoIntakeResult(),
    )

    resultado = agregar_autos([entrada])

    assert any("não confirmada" in aviso for aviso in resultado.avisos)
    assert any("parcial" in aviso for aviso in resultado.avisos)
    campos = {lacuna.campo_alvo for lacuna in resultado.lacunas}
    assert {"tipo_documento", "resumo_fatos", "analise_documental"} <= campos
    assert resultado.cronologia == []
    assert resultado.necessita_revisao_humana is True


def test_entrada_vazia_nao_inventa_conteudo():
    resultado = agregar_autos([])

    assert resultado.indice == []
    assert resultado.partes == []
    assert resultado.pedidos == []
    assert resultado.prazos == []
    assert resultado.estatisticas.documentos == 0
    assert resultado.avisos == ["Nenhum documento foi fornecido ao leitor de autos."]
