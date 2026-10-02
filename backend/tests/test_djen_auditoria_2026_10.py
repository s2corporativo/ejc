"""Regressões da auditoria do módulo DJEN (2026-10).

Cada teste prova um achado corrigido:
  1  comunicação destinada a dois advogados do escritório chega aos dois;
  2  vínculo manual comunicação → caso (inclusive caso encerrado);
  3  janela de reconciliação amplia após parada do job;
  4  evidência oficial (texto íntegro, link, órgão) preservada;
  6  aceitar-prazo valida responsável/data e não duplica sob concorrência;
  7  captura manual usa a mesma resolução de OAB do job e não roda em paralelo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.case import CaseMovimento
from app.models.deadline import Deadline
from app.models.djen import DjenComunicacao
from app.models.user import User, UserRole
from app.routers import intimacoes
from app.services import djen_service

BACKEND = Path(__file__).resolve().parents[1]


# ── Infra de teste ───────────────────────────────────────────────────────────
class _Res:
    def __init__(self, val=None, rows=None):
        self._val = val
        self._rows = rows if rows is not None else []

    def scalar_one_or_none(self):
        return self._val

    def scalar(self):
        return self._val

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, resultados=None):
        self._resultados = list(resultados or [])
        self.statements: list = []
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, *a, **k):
        self.statements.append(stmt)
        return self._resultados.pop(0) if self._resultados else _Res()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        return None


def _user(role=UserRole.advogado, uid="adv-1", **kw) -> User:
    u = User(id=uid, email=f"{uid}@ejc.adv.br", full_name="Adv", role=role, **kw)
    u.is_active = True
    return u


def _com(**kw) -> DjenComunicacao:
    base = dict(
        id="com-1",
        advogado_id="adv-1",
        case_id=None,
        numero_processo="1001234-56.2024.8.13.0024",
        tribunal="TJMG",
        tipo_comunicacao="Intimação",
        texto_resumo="resumo",
        data_disponibilizacao=date(2026, 9, 1),
        prazo_sugerido_status=None,
        prazo_deadline_id=None,
        processada=False,
    )
    base.update(kw)
    return DjenComunicacao(**base)


@pytest.fixture(autouse=True)
def _hoje_fixo(monkeypatch):
    monkeypatch.setattr(intimacoes, "hoje_operacional", lambda: date(2026, 10, 1))


# ── Achado 1 — unicidade por advogado ────────────────────────────────────────
def test_modelo_unico_por_comunicacao_e_advogado():
    indices = {i.name: i for i in DjenComunicacao.__table__.indexes}
    unico = indices["uq_djen_comunicacao_externo_advogado"]
    assert unico.unique
    assert [c.name for c in unico.columns] == ["comunicacao_id_externo", "advogado_id"]
    # a coluna sozinha NÃO pode mais ser única (bloquearia o segundo advogado)
    assert not DjenComunicacao.__table__.c.comunicacao_id_externo.unique
    assert indices["ix_djen_comunicacoes_comunicacao_id_externo"].unique is False


def test_migrations_169_170_expandem_primeiro_e_so_depois_relaxam_a_unicidade():
    m169 = (BACKEND / "alembic/versions/169_djen_multi_advogado.py").read_text()
    m170 = (BACKEND / "alembic/versions/170_djen_remove_unicidade_global.py").read_text()
    assert 'down_revision = "168_finance_ged_links"' in m169
    assert 'down_revision = "169_djen_multi_advogado"' in m170
    # 169: só expande (colunas + índice composto); nada é removido
    assert "uq_djen_comunicacao_externo_advogado" in m169 and "last_ok_at" in m169
    assert "drop_" not in m169.split("def downgrade")[0]
    # 170: relaxa a unicidade global; o downgrade recusa-se com dado replicado
    assert "downgrade 170 recusado" in m170
    for m in (m169, m170):
        assert "DROP TABLE" not in m.upper()


def _patch_captura(monkeypatch, *, casos, inativos=frozenset(), conhecidas=None):
    """conhecidas: {id externo: outra captura já tinha caso?}"""
    conhecidas = dict(conhecidas or {})
    async def _casos(db, numeros):
        return casos

    async def _inat(db, numeros):
        return set(inativos)

    async def _conhecidas(db, externos, advogado_id):
        return conhecidas

    async def _emails(db, ids):
        return {}

    monkeypatch.setattr(djen_service, "buscar_casos_ativos_por_processos", _casos)
    monkeypatch.setattr(djen_service, "buscar_numeros_com_caso_inativo", _inat)
    monkeypatch.setattr(djen_service, "_ids_ja_capturados_por_outros", _conhecidas)
    monkeypatch.setattr(djen_service, "_emails_usuarios", _emails)
    rag = []

    async def _rag(db, item, caso):
        rag.append(item["id"])

    monkeypatch.setattr(djen_service, "_ingerir_rag_do_caso", _rag)
    notificacoes = []

    async def _notif(db, destinatario, titulo, mensagem, **kw):
        notificacoes.append((destinatario, mensagem))

    from app.services import notification_service

    monkeypatch.setattr(notification_service, "criar_notificacao_interna", _notif)
    return rag, notificacoes


def _consulta(*itens):
    return djen_service.DjenConsultaResultado(
        fonte_ok=True, items=list(itens), paginas=1, janela_dias=7
    )


ITEM = {
    "id": "ext-1",
    "numero_processo": "1001234-56.2024.8.13.0024",
    "siglaTribunal": "TJMG",
    "tipoComunicacao": "Intimação",
    "texto": "<p>Fica a parte <b>intimada</b> &amp; ciente.</p>" + ("x" * 3000),
    "link": "https://comunica.pje.jus.br/pdf/ext-1",
    "nomeOrgao": "1ª Vara Cível",
    "dataDisponibilizacao": "2026-09-30",
}


async def test_replica_para_advogado_do_caso_avisa_a_ele_sem_duplicar_efeitos_do_caso(monkeypatch):
    caso = SimpleNamespace(
        id="case-1", client_id="cli",
        advogado_responsavel_id="resp-1", advogado_auxiliar_id="adv-2",
    )
    num = djen_service.normalizar_processo(ITEM["numero_processo"])
    rag, notificacoes = _patch_captura(
        monkeypatch, casos={num: caso}, conhecidas={"ext-1": True}
    )
    db = _FakeDB([_Res(rows=[("uuid-novo", "ext-1")])])

    res = await djen_service._capturar_configurado(
        db, _user(uid="adv-2"), _consulta(ITEM)
    )

    assert res.novas == 1 and res.duplicadas == 0  # a linha do 2º advogado existe
    assert rag == []  # RAG e movimento são por caso: já feitos
    assert [o for o in db.added if isinstance(o, CaseMovimento)] == []
    # ...mas o advogado da réplica é avisado da PRÓPRIA linha (antes: silêncio)
    assert [n[0] for n in notificacoes] == ["adv-2"]


async def test_replica_nao_avisa_duas_vezes_o_responsavel_do_caso(monkeypatch):
    caso = SimpleNamespace(
        id="case-1", client_id="cli",
        advogado_responsavel_id="adv-2", advogado_auxiliar_id=None,
    )
    num = djen_service.normalizar_processo(ITEM["numero_processo"])
    _, notificacoes = _patch_captura(monkeypatch, casos={num: caso}, conhecidas={"ext-1": True})
    db = _FakeDB([_Res(rows=[("uuid", "ext-1")])])
    await djen_service._capturar_configurado(db, _user(uid="adv-2"), _consulta(ITEM))
    assert notificacoes == []  # já foi avisado na primeira captura


async def test_replica_para_advogado_sem_vinculo_nao_herda_case_id_alheio(monkeypatch):
    caso = SimpleNamespace(
        id="case-1", client_id="cli",
        advogado_responsavel_id="resp-1", advogado_auxiliar_id=None,
    )
    num = djen_service.normalizar_processo(ITEM["numero_processo"])
    rag, notificacoes = _patch_captura(
        monkeypatch, casos={num: caso}, conhecidas={"ext-1": True}
    )
    db = _FakeDB([_Res(rows=[("uuid", "ext-1")])])
    await djen_service._capturar_configurado(db, _user(uid="adv-estranho"), _consulta(ITEM))

    valores = db.statements[0].compile().params
    assert next(v for k, v in valores.items() if k.startswith("case_id")) is None
    assert rag == [] and "vincule manualmente" in notificacoes[0][1]


async def test_replica_quando_a_primeira_captura_ficou_sem_caso_ainda_cria_efeitos_do_caso(monkeypatch):
    caso = SimpleNamespace(
        id="case-1", client_id="cli",
        advogado_responsavel_id="resp-1", advogado_auxiliar_id="adv-2",
    )
    num = djen_service.normalizar_processo(ITEM["numero_processo"])
    rag, notificacoes = _patch_captura(
        monkeypatch, casos={num: caso}, conhecidas={"ext-1": False}
    )
    db = _FakeDB([_Res(rows=[("uuid", "ext-1")])])
    await djen_service._capturar_configurado(db, _user(uid="adv-2"), _consulta(ITEM))
    assert rag == ["ext-1"]
    assert len([o for o in db.added if isinstance(o, CaseMovimento)]) == 1
    assert notificacoes[0][0] == "resp-1"


async def test_comunicacao_nova_com_caso_gera_movimento_rag_e_notifica_responsavel(monkeypatch):
    caso = SimpleNamespace(id="case-1", client_id="cli", advogado_responsavel_id="resp-1")
    num = djen_service.normalizar_processo(ITEM["numero_processo"])
    rag, notificacoes = _patch_captura(monkeypatch, casos={num: caso})
    db = _FakeDB([_Res(rows=[("uuid-novo", "ext-1")])])

    res = await djen_service._capturar_configurado(db, _user(), _consulta(ITEM))

    assert res.novas == 1
    assert rag == ["ext-1"]
    assert len([o for o in db.added if isinstance(o, CaseMovimento)]) == 1
    assert notificacoes[0][0] == "resp-1"


async def test_sem_caso_notifica_pedindo_vinculo_manual(monkeypatch):
    _, notificacoes = _patch_captura(monkeypatch, casos={})
    db = _FakeDB([_Res(rows=[("uuid", "ext-1")])])
    await djen_service._capturar_configurado(db, _user(), _consulta(ITEM))
    assert "vincule manualmente" in notificacoes[0][1]


async def test_caso_encerrado_e_sinalizado_na_notificacao(monkeypatch):
    num = djen_service.normalizar_processo(ITEM["numero_processo"])
    _, notificacoes = _patch_captura(monkeypatch, casos={}, inativos={num})
    db = _FakeDB([_Res(rows=[("uuid", "ext-1")])])
    await djen_service._capturar_configurado(db, _user(), _consulta(ITEM))
    assert "ENCERRADO/ARQUIVADO" in notificacoes[0][1]


# ── Achado 4 — evidência oficial ─────────────────────────────────────────────
async def test_evidencia_integral_link_e_orgao_sao_persistidos(monkeypatch):
    _patch_captura(monkeypatch, casos={})
    db = _FakeDB([_Res(rows=[("uuid", "ext-1")])])
    await djen_service._capturar_configurado(db, _user(), _consulta(ITEM))

    valores = db.statements[0].compile().params
    # INSERT em lote: parâmetros sufixados por linha (_m0)
    texto = next(v for k, v in valores.items() if k.startswith("texto_integral"))
    assert "<" not in texto and "&amp;" not in texto and "intimada & ciente" in texto
    assert len(texto) > 2000  # antes truncado em 2000
    assert next(v for k, v in valores.items() if k.startswith("link_oficial")).startswith("https://")
    assert next(v for k, v in valores.items() if k.startswith("orgao")) == "1ª Vara Cível"


def test_link_oficial_rejeita_esquemas_perigosos_e_texto_vazio_e_none():
    assert djen_service._link_oficial({"link": "javascript:alert(1)"}) is None
    assert djen_service._link_oficial({"link": "data:text/html;base64,AAAA"}) is None
    assert djen_service._link_oficial({"link": 5}) is None
    assert djen_service._link_oficial({"link": " https://x.jus.br/a "}) == "https://x.jus.br/a"
    assert djen_service._link_oficial({"link": "http://x.jus.br/a"}) is None  # só https
    assert djen_service._link_oficial({"link": "https://evil.com/x.jus.br"}) is None
    assert djen_service._link_oficial({"link": "https://jus.br.evil.com/a"}) is None
    assert djen_service._texto_integral({"texto": "  "}) is None
    assert djen_service._texto_integral({}) is None
    assert djen_service._texto_integral({"texto": "<script>x()</script>ok"}).endswith("ok")


# ── Achado 3 — janela de reconciliação ───────────────────────────────────────
def _hb(status="ok", horas=2, ok_horas=None):
    agora = datetime.now(timezone.utc)
    return SimpleNamespace(
        last_status=status,
        last_run_at=agora - timedelta(hours=horas),
        last_ok_at=None if ok_horas is None else agora - timedelta(hours=ok_horas),
    )


async def test_janela_padrao_quando_job_saudavel():
    db = _FakeDB([_Res(_hb(ok_horas=2))])
    assert await djen_service.janela_reconciliacao_dias(db) == 7


async def test_janela_mede_desde_o_ultimo_sucesso_real_e_nao_desde_o_ultimo_dado():
    # job falha todo dia (last_run_at recente, status erro) mas o último ok foi há 20 dias
    db = _FakeDB([_Res(_hb(status="erro", horas=3, ok_horas=24 * 20))])
    assert await djen_service.janela_reconciliacao_dias(db) == 22


async def test_janela_respeita_teto_de_90_dias():
    db = _FakeDB([_Res(_hb(status="erro", ok_horas=24 * 400))])
    assert await djen_service.janela_reconciliacao_dias(db) == 90


async def test_janela_linha_antiga_sem_last_ok_usa_last_run_quando_status_ok():
    hb = _hb(status="ok", horas=24 * 15)
    hb.last_ok_at = None
    assert await djen_service.janela_reconciliacao_dias(_FakeDB([_Res(hb)])) == 17
    hb_erro = _hb(status="erro", horas=24 * 15)  # nunca houve sucesso registrado
    assert await djen_service.janela_reconciliacao_dias(_FakeDB([_Res(hb_erro)])) == 7


async def test_janela_nunca_impede_a_captura_e_faz_rollback():
    class _Quebrado:
        rollbacks = 0

        async def execute(self, *a, **k):
            raise RuntimeError("banco indisponível")

        async def rollback(self):
            self.rollbacks += 1

    db = _Quebrado()
    assert await djen_service.janela_reconciliacao_dias(db) == 7
    assert db.rollbacks == 1  # sessão não fica em transação abortada
    assert await djen_service.janela_reconciliacao_dias(_FakeDB([_Res(None)])) == 7


# ── Achado 2 — vínculo manual ────────────────────────────────────────────────
def _liberar_caso(monkeypatch, **caso_kw):
    caso = SimpleNamespace(
        id="case-9",
        numero_processo="1001234-56.2024.8.13.0024",
        advogado_responsavel_id="adv-1",
        advogado_auxiliar_id=None,
        **caso_kw,
    )

    async def _ok(db, cu, case_id):
        return caso

    monkeypatch.setattr(intimacoes, "verificar_acesso_caso", _ok)
    return caso


async def test_vincular_caso_manual_registra_movimento_e_auditoria(monkeypatch):
    _liberar_caso(monkeypatch)
    c = _com()
    db = _FakeDB([_Res(c)])
    out = await intimacoes.vincular_caso(
        "com-1", intimacoes.VincularCasoRequest(case_id="case-9"), db=db, cu=_user()
    )
    assert out["case_id"] == "case-9" and c.case_id == "case-9"
    assert len([o for o in db.added if isinstance(o, CaseMovimento)]) == 1
    aud = [o for o in db.added if isinstance(o, AuditLog)][0]
    assert aud.dados_antes == {"case_id": None}
    assert db.commits == 1


async def test_vincular_caso_com_numero_divergente_exige_confirmacao(monkeypatch):
    caso = _liberar_caso(monkeypatch)
    caso.numero_processo = "9999999-99.2020.8.13.0001"
    c = _com()
    with pytest.raises(HTTPException) as exc:
        await intimacoes.vincular_caso(
            "com-1", intimacoes.VincularCasoRequest(case_id="case-9"),
            db=_FakeDB([_Res(c)]), cu=_user(),
        )
    assert exc.value.status_code == 422 and c.case_id is None

    db = _FakeDB([_Res(c)])
    await intimacoes.vincular_caso(
        "com-1",
        intimacoes.VincularCasoRequest(case_id="case-9", confirmar_divergencia=True),
        db=db, cu=_user(),
    )
    assert c.case_id == "case-9"
    assert [o for o in db.added if isinstance(o, AuditLog)][0].dados_depois["divergencia_confirmada"] is True


async def test_vincular_caso_bloqueado_apos_prazo_aceito(monkeypatch):
    _liberar_caso(monkeypatch)
    c = _com(case_id="case-1", prazo_sugerido_status="aceito", prazo_deadline_id="dl-1")
    with pytest.raises(HTTPException) as exc:
        await intimacoes.vincular_caso(
            "com-1", intimacoes.VincularCasoRequest(case_id="case-9"),
            db=_FakeDB([_Res(c)]), cu=_user(),
        )
    assert exc.value.status_code == 409 and c.case_id == "case-1"


async def test_vincular_caso_de_outro_advogado_e_404():
    c = _com(advogado_id="outro")
    with pytest.raises(HTTPException) as exc:
        await intimacoes.vincular_caso(
            "com-1", intimacoes.VincularCasoRequest(case_id="case-9"),
            db=_FakeDB([_Res(c)]), cu=_user(),
        )
    assert exc.value.status_code == 404


# ── Achado 6 — aceitar-prazo ─────────────────────────────────────────────────
async def test_aceitar_prazo_rejeita_data_no_passado(monkeypatch):
    _liberar_caso(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await intimacoes.aceitar_prazo(
            "com-1",
            intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 9, 30)),
            db=_FakeDB([_Res(_com(case_id="case-9"))]), cu=_user(),
        )
    assert exc.value.status_code == 422 and "passado" in exc.value.detail
    assert "confirmar_prazo_vencido" in exc.value.detail  # diz como registrar o vencido


async def test_prazo_ja_vencido_e_registrado_com_confirmacao_e_fica_auditado(monkeypatch):
    """Intimação capturada com atraso: o vencimento real é passado e precisa ser registrado."""
    _liberar_caso(monkeypatch)
    db = _FakeDB([_Res(_com(case_id="case-9")), _Res(_user(uid="adv-1"))])
    out = await intimacoes.aceitar_prazo(
        "com-1",
        intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 9, 30), confirmar_prazo_vencido=True),
        db=db, cu=_user(),
    )
    prazo = next(o for o in db.added if isinstance(o, Deadline))
    assert out["criado"] is True and prazo.data_prazo == date(2026, 9, 30)
    assert "já vencido" in out["aviso"] and "223" in out["aviso"]
    aud = next(o for o in db.added if isinstance(o, AuditLog))
    assert aud.dados_depois["prazo_vencido_confirmado"] is True


async def test_confirmacao_de_vencido_nao_altera_prazo_futuro(monkeypatch):
    _liberar_caso(monkeypatch)
    db = _FakeDB([_Res(_com(case_id="case-9")), _Res(_user(uid="adv-1"))])
    out = await intimacoes.aceitar_prazo(
        "com-1",
        intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 10, 20), confirmar_prazo_vencido=True),
        db=db, cu=_user(),
    )
    aud = next(o for o in db.added if isinstance(o, AuditLog))
    assert aud.dados_depois["prazo_vencido_confirmado"] is False
    assert out["aviso"] is None


async def test_aceitar_prazo_rejeita_responsavel_inativo_ou_inexistente(monkeypatch):
    _liberar_caso(monkeypatch)
    db = _FakeDB([_Res(_com(case_id="case-9")), _Res(None)])  # usuário não existe
    with pytest.raises(HTTPException) as exc:
        await intimacoes.aceitar_prazo(
            "com-1",
            intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 10, 20), responsavel_id="fantasma"),
            db=db, cu=_user(),
        )
    assert exc.value.status_code == 422
    assert [o for o in db.added if isinstance(o, Deadline)] == []

    inativo = _user(uid="resp-x")
    inativo.is_active = False
    with pytest.raises(HTTPException):
        await intimacoes.aceitar_prazo(
            "com-1",
            intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 10, 20), responsavel_id="resp-x"),
            db=_FakeDB([_Res(_com(case_id="case-9")), _Res(inativo)]), cu=_user(),
        )


async def test_aceitar_prazo_rejeita_responsavel_sem_vinculo_com_o_caso(monkeypatch):
    _liberar_caso(monkeypatch)  # responsável do caso = adv-1
    estranho = _user(uid="adv-estranho")
    with pytest.raises(HTTPException) as exc:
        await intimacoes.aceitar_prazo(
            "com-1",
            intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 10, 20), responsavel_id="adv-estranho"),
            db=_FakeDB([_Res(_com(case_id="case-9")), _Res(estranho)]), cu=_user(),
        )
    assert exc.value.status_code == 422 and "vínculo" in exc.value.detail


async def test_responsavel_padrao_inativo_cai_no_responsavel_do_caso_e_depois_em_quem_aceita(monkeypatch):
    _liberar_caso(monkeypatch)  # responsável do caso = adv-1
    inativo = _user(uid="adv-antigo")
    inativo.is_active = False
    resp_caso = _user(uid="adv-1")
    # advogado da intimação (inativo) -> responsável do caso (válido)
    db = _FakeDB([_Res(_com(case_id="case-9", advogado_id="adv-antigo")), _Res(inativo), _Res(resp_caso)])
    await intimacoes.aceitar_prazo(
        "com-1", intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 10, 20)),
        db=db, cu=_user(uid="socio-1", role=UserRole.socio),
    )
    assert next(o for o in db.added if isinstance(o, Deadline)).responsavel_id == "adv-1"

    # nenhum candidato válido -> quem aceita (já passou por verificar_acesso_caso)
    db2 = _FakeDB([_Res(_com(case_id="case-9", advogado_id="adv-antigo")), _Res(inativo), _Res(None)])
    await intimacoes.aceitar_prazo(
        "com-1", intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 10, 20)),
        db=db2, cu=_user(uid="socio-1", role=UserRole.socio),
    )
    assert next(o for o in db2.added if isinstance(o, Deadline)).responsavel_id == "socio-1"


async def test_aceitar_prazo_avisa_fim_de_semana_e_usa_lock(monkeypatch):
    _liberar_caso(monkeypatch)
    db = _FakeDB([_Res(_com(case_id="case-9")), _Res(_user(uid="adv-1"))])
    out = await intimacoes.aceitar_prazo(
        "com-1",
        intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 10, 10)),  # sábado
        db=db, cu=_user(),
    )
    assert out["criado"] is True and "224" in out["aviso"]
    assert "FOR UPDATE" in str(db.statements[0].compile()).upper()  # sem aceite duplo


# ── Achado 7 — captura manual ────────────────────────────────────────────────
async def test_captura_manual_aceita_oab_de_perfil_como_o_job(monkeypatch):
    visto = {}

    async def _cap(db, adv, *, dias):
        visto["dias"] = dias
        return djen_service.DjenCapturaResultado(
            configurada=True, fonte_ok=True, recebidas=0, novas=0, duplicadas=0, ignoradas=0
        )

    async def _enviar(res):
        return None

    monkeypatch.setattr(intimacoes, "capturar_para_advogado", _cap)
    monkeypatch.setattr(intimacoes, "enviar_emails_pendentes", _enviar)
    usuario = _user(oab_number="252599/MG")  # sem djen_oab_*
    out = await intimacoes.capturar_agora(dias=30, db=_FakeDB(), cu=usuario)
    assert visto["dias"] == 30 and out["novas"] == 0
    assert usuario.id not in intimacoes._capturas_manuais_em_curso  # liberou a trava


async def test_captura_manual_limita_janela_da_equipe_a_30_dias_e_gestao_ate_90(monkeypatch):
    vistos = []

    async def _cap(db, adv, *, dias):
        vistos.append(dias)
        return djen_service.DjenCapturaResultado(
            configurada=True, fonte_ok=True, recebidas=0, novas=0, duplicadas=0, ignoradas=0
        )

    async def _enviar(res):
        return None

    monkeypatch.setattr(intimacoes, "capturar_para_advogado", _cap)
    monkeypatch.setattr(intimacoes, "enviar_emails_pendentes", _enviar)
    await intimacoes.capturar_agora(dias=90, db=_FakeDB(), cu=_user(djen_oab_numero="1", djen_oab_uf="MG"))
    await intimacoes.capturar_agora(
        dias=90, db=_FakeDB(),
        cu=_user(role=UserRole.socio, uid="socio-1", djen_oab_numero="1", djen_oab_uf="MG"),
    )
    assert vistos == [30, 90]


async def test_captura_manual_sem_oab_resolvivel_e_422():
    with pytest.raises(HTTPException) as exc:
        await intimacoes.capturar_agora(dias=7, db=_FakeDB(), cu=_user(oab_number="252599"))
    assert exc.value.status_code == 422


async def test_captura_manual_concorrente_e_recusada_e_trava_e_liberada_em_erro(monkeypatch):
    usuario = _user(djen_oab_numero="123456", djen_oab_uf="MG")
    intimacoes._capturas_manuais_em_curso.add(usuario.id)
    try:
        with pytest.raises(HTTPException) as exc:
            await intimacoes.capturar_agora(dias=7, db=_FakeDB(), cu=usuario)
        assert exc.value.status_code == 409
    finally:
        intimacoes._capturas_manuais_em_curso.discard(usuario.id)

    async def _falha(db, adv, *, dias):
        return djen_service.DjenCapturaResultado.falha_interna()

    monkeypatch.setattr(intimacoes, "capturar_para_advogado", _falha)
    db = _FakeDB()
    with pytest.raises(HTTPException) as exc:
        await intimacoes.capturar_agora(dias=7, db=db, cu=usuario)
    assert exc.value.status_code == 503 and db.rollbacks == 1
    assert usuario.id not in intimacoes._capturas_manuais_em_curso


def test_captura_manual_tem_rate_limit_declarado():
    rota = next(r for r in intimacoes.router.routes if r.path.endswith("/capturar-agora"))
    nomes = [str(getattr(d.call, "__qualname__", "")) for d in rota.dependant.dependencies]
    assert any("rate_limit" in n for n in nomes)


# ── Baixa — status-captura e escopo ──────────────────────────────────────────
async def test_contagem_recente_filtra_por_advogado_para_nao_gestao():
    db = _FakeDB([_Res(3)])
    assert await intimacoes._contar_recentes(db, _user(), datetime.now(timezone.utc)) == 3
    assert "advogado_id" in str(db.statements[0].compile()).lower()

    db2 = _FakeDB([_Res(9)])
    socio = _user(role=UserRole.socio, uid="socio-1")
    await intimacoes._contar_recentes(db2, socio, datetime.now(timezone.utc))
    assert "advogado_id" not in str(db2.statements[0].compile()).lower().split("where")[-1]


def test_aviso_de_escopo_declara_limite_da_fonte():
    assert "ausência" in intimacoes.AVISO_ESCOPO_DJEN
    assert "DJEN" in intimacoes.AVISO_ESCOPO_DJEN
