"""Serialização dos POST de ramos — não vaza estado interno do ORM.

Regressão do pente fino (2026-07): os handlers de criação dos 6 ramos
(empresarial/cível/penal/trabalhista/administrativo/bancário) retornavam
`obj.__dict__`, que inclui a chave privada `_sa_instance_state` do SQLAlchemy
(objeto interno, não serializável e sem valor para o cliente). O helper
`_serialize` do próprio módulo devolve apenas as colunas mapeadas.
"""
from app.routers.ramos import _serialize
from app.models.especializado import EmpresarialCase


def test_serialize_nao_vaza_sa_instance_state():
    obj = EmpresarialCase(id="doc-1", case_id="case-1")

    # `__dict__` cru vaza o estado interno do ORM — é justamente o bug evitado.
    assert "_sa_instance_state" in obj.__dict__

    data = _serialize(obj)
    assert "_sa_instance_state" not in data
    # Só colunas mapeadas, e com os valores esperados.
    assert data["id"] == "doc-1"
    assert data["case_id"] == "case-1"
    assert set(data.keys()) == {c.key for c in EmpresarialCase.__table__.columns}
