"""Curadoria da reclassificação de área dos casos históricos.

Trava o critério de decisão (quem é candidato, com que confiança), a
idempotência e a garantia central do script: SEM --aplicar não existe escrita.

Não exige Postgres — a lógica de decisão vive num módulo puro
(scripts/reclassificacao_areas.py) e a casca é exercitada com uma conexão
falsa que registra todo SQL executado.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

logica = _carregar("reclassificacao_areas", SCRIPTS / "reclassificacao_areas.py")
casca = _carregar("reclassificar_areas_casos", SCRIPTS / "reclassificar_areas_casos.py")

CasoBruto = logica.CasoBruto
Nivel = logica.Nivel


def caso(**kw) -> "logica.CasoBruto":
    base = {"case_id": kw.pop("case_id", "c1"), "area": kw.pop("area", "civil")}
    return CasoBruto(**base, **kw)


# ── Nível ALTA: satélite determina a área ────────────────────────────────────
def test_civil_com_satelite_bancario_e_alta_para_bancario():
    d = logica.classificar_caso(caso(tem_bancario_esp=True))
    assert (d.nivel, d.area_nova, d.elegivel) == (Nivel.ALTA, "bancario", True)
    assert "bancario_cases" in d.evidencia


def test_tributario_com_admin_de_tipo_exclusivo_e_alta_para_administrativo():
    d = logica.classificar_caso(
        caso(area="tributario", admin_tipos=("servidor_publico",))
    )
    assert (d.nivel, d.area_nova, d.elegivel) == (Nivel.ALTA, "administrativo", True)


# ── Nível AMBÍGUO: sinal existe mas não decide ───────────────────────────────
def test_admin_de_tipo_compartilhado_com_hub_tributario_nunca_e_aplicavel():
    """`recurso_multa_tributaria` é oferecido pelos hubs Administrativo E
    Tributário — o satélite não prova de qual hub veio."""
    d = logica.classificar_caso(
        caso(area="tributario", admin_tipos=("recurso_multa_tributaria",))
    )
    assert d.nivel == Nivel.AMBIGUA
    assert d.area_nova is None and not d.elegivel


def test_dois_satelites_de_areas_diferentes_saem_ambiguos():
    d = logica.classificar_caso(caso(tem_bancario_esp=True, tem_civel_esp=True))
    assert d.nivel == Nivel.AMBIGUA
    assert d.area_nova is None and not d.elegivel
    assert d.regra == "sinais_conflitantes"


def test_sinal_que_aponta_fora_do_mandato_nao_vira_proposta():
    """Caso `civil` com satélite administrativo: administrativo NÃO é um
    de-achatamento de civil. O script não reclassifica além do seu mandato."""
    d = logica.classificar_caso(caso(admin_tipos=("recurso_multa_transito",)))
    assert d.nivel == Nivel.AMBIGUA
    assert d.area_nova is None


# ── Nível MÉDIO: circunstancial, nunca aplicado ──────────────────────────────
def test_analise_de_extrato_sozinha_e_media_e_nao_e_elegivel():
    d = logica.classificar_caso(caso(qtd_analises_bancarias=3))
    assert (d.nivel, d.area_nova) == (Nivel.MEDIA, "bancario")
    assert not d.elegivel


def test_caso_areas_principal_divergente_e_media():
    d = logica.classificar_caso(caso(areas_principais_declaradas=("imobiliario",)))
    assert (d.nivel, d.area_nova) == (Nivel.MEDIA, "imobiliario")
    assert not d.elegivel


def test_caso_areas_principal_fora_do_mandato_e_ignorado():
    d = logica.classificar_caso(caso(areas_principais_declaradas=("ambiental",)))
    assert d.nivel == Nivel.SEM_SINAL


# ── Sem sinal / confirmado ───────────────────────────────────────────────────
def test_civil_sem_nenhum_sinal_e_sem_sinal():
    d = logica.classificar_caso(caso())
    assert d.nivel == Nivel.SEM_SINAL and d.area_nova is None


@pytest.mark.parametrize(
    "area,campo",
    [("civil", "tem_civel_esp"), ("empresarial", "tem_empresarial_esp")],
)
def test_satelite_do_proprio_hub_confirma_a_area_atual(area, campo):
    """O hub Cível grava `civil` inclusive depois da correção — um
    civel_cases com tipo `imobiliario_locacao` CONFIRMA civil, não é
    candidato a virar imobiliário."""
    d = logica.classificar_caso(caso(area=area, **{campo: True}))
    assert d.nivel == Nivel.CONFIRMADO and d.area_nova is None


def test_digital_lgpd_nunca_e_proposto_automaticamente():
    """Nenhum satélite distingue digital_lgpd de empresarial (o ROPA da LGPD
    é por cliente, não por caso)."""
    decisoes = [
        logica.classificar_caso(caso(case_id="a", area="empresarial")),
        logica.classificar_caso(
            caso(case_id="b", area="empresarial", qtd_analises_bancarias=1)
        ),
    ]
    assert all(d.area_nova != "digital_lgpd" for d in decisoes)
    assert not any(d.elegivel for d in decisoes)


# ── Idempotência ─────────────────────────────────────────────────────────────
def test_caso_ja_na_area_correta_e_ignorado():
    d = logica.classificar_caso(caso(area="bancario", tem_bancario_esp=True))
    assert d.nivel == Nivel.CONFIRMADO and d.area_nova is None
    assert not d.elegivel


def test_segunda_passada_nao_propoe_nada():
    casos = [caso(case_id="c1", tem_bancario_esp=True),
             caso(case_id="c2", area="tributario", admin_tipos=("desapropriacao",))]
    primeira = logica.selecionar_para_aplicar(logica.classificar(casos))
    assert len(primeira) == 2

    aplicado = {d.case_id: d.area_nova for d in primeira}
    depois = [
        CasoBruto(
            case_id=c.case_id, area=aplicado.get(c.case_id, c.area),
            tem_bancario_esp=c.tem_bancario_esp, admin_tipos=c.admin_tipos,
        )
        for c in casos
    ]
    assert logica.selecionar_para_aplicar(logica.classificar(depois)) == []


# ── Seleção e taxonomia ──────────────────────────────────────────────────────
def test_selecionar_para_aplicar_so_pega_alta_e_respeita_limite():
    casos = [
        caso(case_id="a1", tem_bancario_esp=True),
        caso(case_id="a2", tem_bancario_esp=True),
        caso(case_id="m1", qtd_analises_bancarias=1),
        caso(case_id="x1"),
    ]
    decisoes = logica.classificar(casos)
    assert [d.case_id for d in logica.selecionar_para_aplicar(decisoes)] == ["a1", "a2"]
    assert [d.case_id for d in logica.selecionar_para_aplicar(decisoes, 1)] == ["a1"]


def test_tipos_compartilhados_ficam_fora_do_conjunto_exclusivo():
    compartilhados = {
        "recurso_multa_tributaria", "recurso_multa_sanitaria",
        "recurso_autuacao_mte", "mandado_seguranca_admin", "outro_admin",
        "recurso_multa_ambiental",
    }
    assert not (logica.TIPOS_EXCLUSIVOS_ADMINISTRATIVO & compartilhados)
    assert "servidor_publico" in logica.TIPOS_EXCLUSIVOS_ADMINISTRATIVO


def test_areas_achatadas_batem_com_o_enum_case_area():
    """Se o enum mudar, o mapa de de-achatamento tem de acompanhar."""
    from app.models.case import CaseArea

    validas = {a.value for a in CaseArea}
    assert set(logica.DE_ACHATAMENTO) <= validas
    for alvos in logica.DE_ACHATAMENTO.values():
        assert set(alvos) <= validas


# ── Casca: simulação não escreve ─────────────────────────────────────────────
class _FakeCursor:
    def __init__(self, registro: list[str], linhas: dict[str, list]):
        self._registro = registro
        self._linhas = linhas
        self._atual: list = []
        self.description = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._registro.append(sql)
        if "FROM cases c" in sql:
            self.description = [(c,) for c in _COLUNAS]
            self._atual = self._linhas["candidatos"]
        elif "GROUP BY" in sql:
            self.description = [("area",), ("n",)]
            self._atual = self._linhas["totais"]
        else:
            self._atual = []
            self.rowcount = 1

    def fetchall(self):
        return self._atual


class _FakeConn:
    def __init__(self, linhas):
        self.sqls: list[str] = []
        self._linhas = linhas
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self.sqls, self._linhas)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


_COLUNAS = [
    "id", "area", "titulo", "tem_bancario", "tem_civel", "tem_empresarial",
    "tem_penal", "tem_trabalhista", "admin_tipos", "qtd_analises",
    "areas_principais",
]


def _linha_candidato(cid: str, area: str, **kw):
    valores = {
        "id": cid, "area": area, "titulo": "Caso X", "tem_bancario": False,
        "tem_civel": False, "tem_empresarial": False, "tem_penal": False,
        "tem_trabalhista": False, "admin_tipos": [], "qtd_analises": 0,
        "areas_principais": [],
    }
    valores.update(kw)
    return tuple(valores[c] for c in _COLUNAS)


def _escritas(sqls: list[str]) -> list[str]:
    return [
        s for s in sqls
        if any(v in s.upper() for v in ("UPDATE ", "INSERT ", "DELETE ", "DROP "))
    ]


@pytest.fixture
def conexao_falsa(monkeypatch):
    linhas = {
        "totais": [("civil", 10), ("bancario", 2)],
        "candidatos": [
            _linha_candidato("c1", "civil", tem_bancario=True),
            _linha_candidato("c2", "civil"),
            _linha_candidato("c3", "tributario", admin_tipos=["desapropriacao"]),
        ],
    }
    conn = _FakeConn(linhas)
    monkeypatch.setattr(casca, "conectar", lambda url: conn)
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://u:p@localhost:5432/ejc_db")
    monkeypatch.delenv("APP_ENV", raising=False)
    return conn


def test_simulacao_e_o_padrao_e_nao_executa_nenhuma_escrita(conexao_falsa, capsys):
    assert casca.main([]) == 0
    assert _escritas(conexao_falsa.sqls) == []
    assert conexao_falsa.commits == 0
    saida = capsys.readouterr().out
    assert "SIMULAÇÃO — NADA FOI ESCRITO" in saida
    assert "ELEGÍVEIS A --aplicar (nível alta): 2" in saida


def test_simulacao_nao_vaza_titulo_sem_a_flag(conexao_falsa, capsys):
    casca.main([])
    assert "Caso X" not in capsys.readouterr().out


def test_incluir_titulo_avisa_que_a_saida_tem_dado_do_escritorio(conexao_falsa, capsys):
    casca.main(["--incluir-titulo"])
    saida = capsys.readouterr().out
    assert "dado do escritório" in saida.lower() or "DADO DO ESCRITÓRIO" in saida
    assert "Caso X" in saida


def test_aplicar_sem_confirmacao_interativa_nao_escreve(conexao_falsa, monkeypatch):
    monkeypatch.setattr(casca, "confirmar_interativo", lambda *a, **k: False)
    assert casca.main(["--aplicar"]) == 1
    assert _escritas(conexao_falsa.sqls) == []


def test_aplicar_confirmado_escreve_e_grava_rollback(conexao_falsa, monkeypatch, tmp_path):
    monkeypatch.setattr(casca, "confirmar_interativo", lambda *a, **k: True)
    arquivo = tmp_path / "rb.json"
    assert casca.main(["--aplicar", "--saida-rollback", str(arquivo)]) == 0

    updates = [s for s in conexao_falsa.sqls if "UPDATE cases" in s]
    assert len(updates) == 2  # só os dois de nível alta

    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    assert dados["status"] == "aplicado" and dados["aplicados"] == 2
    assert {i["case_id"]: (i["area_anterior"], i["area_nova"]) for i in dados["itens"]} == {
        "c1": ("civil", "bancario"),
        "c3": ("tributario", "administrativo"),
    }
    assert "u:p@" not in json.dumps(dados)  # credencial nunca vai para o arquivo


def test_rollback_e_gravado_antes_do_primeiro_update(conexao_falsa, monkeypatch, tmp_path):
    arquivo = tmp_path / "rb.json"
    visto: list[bool] = []
    execute_original = _FakeCursor.execute

    def espiao(self, sql, params=None):
        if "UPDATE cases" in sql:
            visto.append(arquivo.exists())
        return execute_original(self, sql, params)

    monkeypatch.setattr(_FakeCursor, "execute", espiao)
    monkeypatch.setattr(casca, "confirmar_interativo", lambda *a, **k: True)
    casca.main(["--aplicar", "--saida-rollback", str(arquivo)])
    assert visto and all(visto), "o arquivo de rollback tem de existir antes do 1º UPDATE"


def test_limite_reduz_o_que_e_aplicado(conexao_falsa, monkeypatch, tmp_path):
    monkeypatch.setattr(casca, "confirmar_interativo", lambda *a, **k: True)
    arquivo = tmp_path / "rb.json"
    casca.main(["--aplicar", "--limite", "1", "--saida-rollback", str(arquivo)])
    assert len([s for s in conexao_falsa.sqls if "UPDATE cases" in s]) == 1


def test_reverter_restaura_exatamente_o_arquivo(conexao_falsa, monkeypatch, tmp_path):
    arquivo = tmp_path / "rb.json"
    arquivo.write_text(json.dumps({
        "versao": 1, "tipo": "reclassificacao_area_cases", "status": "aplicado",
        "itens": [{"case_id": "c1", "area_anterior": "civil",
                   "area_nova": "bancario", "regra": "satelite_bancario"}],
    }), encoding="utf-8")
    monkeypatch.setattr(casca, "confirmar_interativo", lambda *a, **k: True)
    assert casca.main(["--reverter", str(arquivo)]) == 0
    assert json.loads(arquivo.read_text(encoding="utf-8"))["status"] == "revertido"


def test_reverter_recusa_arquivo_estranho(conexao_falsa, monkeypatch, tmp_path):
    arquivo = tmp_path / "outro.json"
    arquivo.write_text(json.dumps({"tipo": "qualquer", "itens": []}), encoding="utf-8")
    monkeypatch.setattr(casca, "confirmar_interativo", lambda *a, **k: True)
    with pytest.raises(SystemExit):
        casca.main(["--reverter", str(arquivo)])


# ── Guarda de produção ───────────────────────────────────────────────────────
@pytest.mark.parametrize("url,esperado", [
    ("postgresql://u:p@localhost:5432/ejc_db", False),
    ("postgresql://u:p@db:5432/ejc_db", False),
    ("postgresql://u:p@10.0.0.9:5432/ejc_db", True),
    ("postgresql://u:p@localhost:5432/ejc_prod", True),
])
def test_deteccao_de_producao(url, esperado, monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    assert casca.parece_producao(url)[0] is esperado


def test_producao_bloqueia_aplicar_sem_flag_explicita(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://u:p@10.0.0.9:5432/ejc_db")
    monkeypatch.setattr(casca, "conectar", lambda url: pytest.fail("não deve conectar"))
    with pytest.raises(SystemExit) as exc:
        casca.main(["--aplicar"])
    assert "produ" in str(exc.value).lower()


def test_producao_nao_bloqueia_simulacao(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://u:p@10.0.0.9:5432/ejc_db")
    conn = _FakeConn({"totais": [], "candidatos": []})
    monkeypatch.setattr(casca, "conectar", lambda url: conn)
    assert casca.main([]) == 0
    assert _escritas(conn.sqls) == []


def test_sem_interacao_exige_referencia_de_backup(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://u:p@localhost:5432/ejc_db")
    monkeypatch.setattr(casca, "conectar", lambda url: pytest.fail("não deve conectar"))
    with pytest.raises(SystemExit) as exc:
        casca.main(["--aplicar", "--sem-interacao"])
    assert "backup" in str(exc.value).lower()


def test_descrever_banco_nao_expoe_credencial():
    assert casca.descrever_banco("postgresql://user:senha@host:5433/ejc") == "host:5433/ejc"
