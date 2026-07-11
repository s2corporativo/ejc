"""Dossiê Estratégico — módulos determinísticos (sem IA): serialização da
linha do tempo, mapa probatório (Prova ↔ Tese), riscos (case_health) e teses
estruturadas. Testes unitários das funções puras com fakes (sem banco),
no padrão de tests/test_visual_law.py."""
from datetime import date, datetime, timezone

from app.services import dossie_modulos as dm


# ── serializar_eventos ────────────────────────────────────────────────────────

def test_serializar_eventos_converte_datas_e_limita():
    eventos = [
        {"data": datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
         "categoria": "movimento", "tipo": "despacho", "descricao": "Despacho"},
        {"data": date(2026, 6, 15), "categoria": "prazo",
         "tipo": "recurso", "descricao": "Prazo recursal"},
        {"data": None, "categoria": "documento", "tipo": "doc", "descricao": "Sem data"},
    ]
    out = dm.serializar_eventos(eventos, limite=2)
    assert len(out) == 2  # respeita o limite
    assert out[0]["data"] == "2026-07-01T12:00:00+00:00"
    assert out[1]["data"] == "2026-06-15"
    # não muta o original
    assert isinstance(eventos[0]["data"], datetime)


def test_serializar_eventos_data_none_vira_none():
    out = dm.serializar_eventos([{"data": None, "categoria": "x",
                                  "tipo": "y", "descricao": "z"}])
    assert out[0]["data"] is None


# ── montar_mapa_probatorio ────────────────────────────────────────────────────

def _prova(id="p1", tipo="documental", titulo="Contrato", fato="Prova o vínculo",
           tese_id=None, ordem=0):
    return {"id": id, "tipo": tipo, "titulo": titulo,
            "fato_probando": fato, "tese_id": tese_id, "ordem": ordem}


def test_mapa_probatorio_vincula_tese_e_conta_tipos():
    provas = [
        _prova(id="p2", tipo="testemunhal", titulo="Testemunha A",
               fato="Presenciou o acidente", tese_id="t1", ordem=2),
        _prova(id="p1", tipo="documental", titulo="Contrato",
               fato="Prova o vínculo", ordem=1),
        _prova(id="p3", tipo="documental", titulo="E-mail", fato="  ", ordem=3),
    ]
    mapa = dm.montar_mapa_probatorio(provas, {"t1": "Responsabilidade objetiva"})
    assert mapa["total"] == 3
    # ordenado pela ordem do Documento Único de Anexos
    assert [p["id"] for p in mapa["provas"]] == ["p1", "p2", "p3"]
    assert mapa["por_tipo"] == {"documental": 2, "testemunhal": 1}
    # vínculo prova → tese resolvido por título
    p2 = mapa["provas"][1]
    assert p2["tese_id"] == "t1"
    assert p2["tese_titulo"] == "Responsabilidade objetiva"
    # prova sem tese: campos nulos (não inventa vínculo)
    assert mapa["provas"][0]["tese_titulo"] is None
    # fato_probando em branco conta como lacuna e vira None
    assert mapa["sem_fato_probando"] == 1
    assert mapa["provas"][2]["fato_probando"] is None


def test_mapa_probatorio_vazio_nao_sugere_faltantes():
    mapa = dm.montar_mapa_probatorio([], {})
    assert mapa == {"total": 0, "provas": [], "por_tipo": {},
                    "sem_fato_probando": 0}
    # slot de outro módulo: mapa NÃO carrega provas_faltantes
    assert "provas_faltantes" not in mapa


def test_mapa_probatorio_tese_desconhecida_titulo_none():
    mapa = dm.montar_mapa_probatorio([_prova(tese_id="t-orfa")], {})
    assert mapa["provas"][0]["tese_id"] == "t-orfa"
    assert mapa["provas"][0]["tese_titulo"] is None


# ── classificar_riscos ────────────────────────────────────────────────────────

def test_classificar_riscos_ordena_por_gravidade_e_da_severidade():
    saude = {
        "score": 45, "classificacao": "risco", "dias_parado": 40,
        "fatores": [
            {"fator": "sem_posmortem", "impacto": -5, "detalhe": "d1"},
            {"fator": "prazo_vencido", "impacto": -20, "detalhe": "d2"},
            {"fator": "sem_procuracao", "impacto": -10, "detalhe": "d3"},
            {"fator": "sem_movimentacao", "impacto": -15, "detalhe": "d4"},
        ],
    }
    riscos = dm.classificar_riscos(saude)
    assert riscos["score"] == 45
    assert riscos["classificacao"] == "risco"
    assert riscos["dias_parado"] == 40
    assert riscos["saudavel"] is False
    # mais grave primeiro
    assert [f["fator"] for f in riscos["fatores"]] == [
        "prazo_vencido", "sem_movimentacao", "sem_procuracao", "sem_posmortem"]
    # severidade: ≤ −15 alta · ≤ −10 media · resto baixa
    assert [f["severidade"] for f in riscos["fatores"]] == [
        "alta", "alta", "media", "baixa"]


def test_classificar_riscos_saudavel_sem_fatores():
    riscos = dm.classificar_riscos(
        {"score": 100, "classificacao": "saudavel", "dias_parado": None,
         "fatores": []})
    assert riscos["saudavel"] is True
    assert riscos["fatores"] == []
    assert riscos["dias_parado"] == 0  # None normalizado


# ── estruturar_teses ──────────────────────────────────────────────────────────

def test_estruturar_teses_primeira_vinculada_e_principal():
    teses = [{"id": "t1", "titulo": "Principal"},
             {"id": "t2", "titulo": "Sub 1"},
             {"id": "t3", "titulo": "Sub 2"}]
    out = dm.estruturar_teses(teses)
    assert out["principal"]["id"] == "t1"
    assert [t["id"] for t in out["subsidiarias"]] == ["t2", "t3"]
    assert out["total"] == 3


def test_estruturar_teses_vazio():
    assert dm.estruturar_teses([]) == {"principal": None,
                                       "subsidiarias": [], "total": 0}


def test_estruturar_teses_unica_sem_subsidiarias():
    out = dm.estruturar_teses([{"id": "t1", "titulo": "Única"}])
    assert out["principal"]["id"] == "t1"
    assert out["subsidiarias"] == []


# ── modulos_para_html (PDF · tema Visual Law) ─────────────────────────────────

def _modulos_minimos(**extra):
    base = {
        "linha_do_tempo": {
            "fase_atual": "conhecimento",
            "fases": [{"fase": "pre_processual", "label": "Pré-processual",
                       "status": "concluida"},
                      {"fase": "conhecimento", "label": "Conhecimento",
                       "status": "atual"}],
            "eventos": [{"data": "2026-07-01T12:00:00+00:00",
                         "categoria": "movimento", "tipo": "despacho",
                         "descricao": "Despacho <script>"}],
            "proximos_passos": [{"titulo": "Sentença", "origem": "estimativa",
                                 "data_estimada": None, "detalhe": "…"}],
            "estagnacao": {"dias_parado": 10, "nivel": "ok"},
        },
        "mapa_probatorio": {
            "total": 1, "sem_fato_probando": 0,
            "provas": [{"id": "p1", "tipo": "documental", "titulo": "Contrato",
                        "fato_probando": "Vínculo", "tese_id": "t1",
                        "tese_titulo": "Tese X"}],
            "por_tipo": {"documental": 1},
        },
        "riscos": {"score": 80, "classificacao": "saudavel", "dias_parado": 10,
                   "fatores": [], "saudavel": True},
        "teses": {"principal": {"id": "t1", "titulo": "Tese X",
                                "descricao": "Desc"},
                  "subsidiarias": [{"id": "t2", "titulo": "Tese Y"}],
                  "total": 2},
    }
    base.update(extra)
    return base


def test_modulos_para_html_secoes_e_escape():
    html = dm.modulos_para_html(_modulos_minimos())
    for secao in ("LINHA DO TEMPO", "PROVAS EXISTENTES", "RISCOS", "TESES"):
        assert secao in html
    assert "Tese X" in html and "Tese Y" in html
    assert "80/100" in html
    # conteúdo do banco é escapado (WeasyPrint recebe HTML)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    # sem provas_faltantes no payload → seção ausente (slot de outro módulo)
    assert "PROVAS FALTANTES" not in html


def test_modulos_para_html_renderiza_provas_faltantes_quando_presentes():
    html = dm.modulos_para_html(_modulos_minimos(
        provas_faltantes=[{"titulo": "Laudo pericial"}, "Ata notarial"]))
    assert "PROVAS FALTANTES" in html
    assert "Laudo pericial" in html
    assert "Ata notarial" in html


def test_modulos_para_html_estados_vazios_nao_quebram():
    html = dm.modulos_para_html({
        "linha_do_tempo": {"fases": [], "eventos": [], "proximos_passos": [],
                           "estagnacao": {}},
        "mapa_probatorio": {"total": 0, "provas": [], "por_tipo": {},
                            "sem_fato_probando": 0},
        "riscos": {"score": None, "classificacao": None, "fatores": []},
        "teses": {"principal": None, "subsidiarias": [], "total": 0},
    })
    assert "Nenhuma prova cadastrada" in html
    assert "Nenhuma tese vinculada" in html
    assert "Nenhum fator de risco" in html
