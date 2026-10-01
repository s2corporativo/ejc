"""Metadados OpenAPI preservados na composição por cópia de app/routers/ramos.py.

Regressão da pendência da Task 23 (worklog, Onda 27c): o agregador ramos.py
compõe os 9 sub-routers ramos_* copiando cada APIRoute via add_api_route
(9 loops). Medição no estado anterior revelou duas degradações reais:

1. TAGS DUPLICADAS em 82/82 rotas: add_api_route soma as tags default do
   agregador ("Áreas de Atuação") às tags repassadas da origem — que JÁ
   continham as tags default do sub-router de origem. Toda rota copiada
   ficava com ['Áreas de Atuação', 'Áreas de Atuação'] no OpenAPI.
2. Campos de metadado NÃO repassados: description/responses/operation_id/
   response_class/include_in_schema/openapi_extra/name não eram passados na
   cópia e só coincidiam porque os defaults derivam do mesmo endpoint —
   qualquer rota de origem que os declarasse os perderia silenciosamente.

A correção repassa os 9 campos e envia apenas o DELTA de tags (as tags
default do agregador já são aplicadas pelo próprio add_api_route).

O teste compara atributo a atributo cada APIRoute de ORIGEM × CÓPIA — mesmo
critério do script de verificação scripts/verifica_openapi_ramos.py (FORA do
repo). Inspeção pura de rotas: não precisa de banco nem de rede.
"""
from fastapi.routing import APIRoute

from app.routers import ramos as agregador
from app.routers import (
    ramos_admin_esp,
    ramos_bancario,
    ramos_civel,
    ramos_empresarial,
    ramos_ferramentas_complementares,
    ramos_penal,
    ramos_tributario_paf,
    ramos_trabalhista_esp,
    ramos_vitrine,
)

# Path legado NÃO montado pelo agregador canônico (substituído pelo PAF
# federal versionado; ver comentário no próprio ramos.py).
_EXCLUIDAS = {ramos_tributario_paf.ROTA_AUTO_INFRACAO}

_FONTES = [
    ramos_empresarial.router,
    ramos_civel.router,
    ramos_penal.router,
    ramos_trabalhista_esp.router,
    ramos_admin_esp.router,
    ramos_bancario.router,
    ramos_vitrine.router,
    ramos_tributario_paf.router,
    ramos_ferramentas_complementares.router,
]

# Todos os metadados declaráveis de uma APIRoute que a cópia deve preservar
# (path/endpoint/methods/dependencies já eram repassados desde sempre).
CAMPOS = (
    "name",
    "summary",
    "description",
    "response_model",
    "status_code",
    "tags",
    "deprecated",
    "operation_id",
    "responses",
    "response_class",
    "include_in_schema",
    "openapi_extra",
)


def _chave(rota: APIRoute):
    return (rota.path, tuple(sorted(rota.methods)))


def _rotas_copia() -> dict:
    copias: dict = {}
    for rota in agregador.router.routes:
        if isinstance(rota, APIRoute):
            copias.setdefault(_chave(rota), []).append(rota)
    return copias


def test_copia_preserva_metadados_openapi_rota_a_rota():
    copias = _rotas_copia()
    inspecionadas = 0
    for router_fonte in _FONTES:
        for origem in router_fonte.routes:
            if getattr(origem, "path", None) is None:
                continue
            if origem.path in _EXCLUIDAS and router_fonte is ramos_ferramentas_complementares.router:
                continue
            fila = copias.get(_chave(origem))
            assert fila, f"rota de origem SEM cópia no agregador: {origem.methods} {origem.path}"
            copia = fila.pop(0)
            for campo in CAMPOS:
                assert getattr(copia, campo) == getattr(origem, campo), (
                    f"metadado '{campo}' divergiu na cópia de "
                    f"{sorted(origem.methods)} {origem.path}: "
                    f"origem={getattr(origem, campo)!r} cópia={getattr(copia, campo)!r}"
                )
            inspecionadas += 1
    # Sanidade da comparação: as 82 rotas mapeadas hoje precisam estar cobertas
    # (se um ramos_* ganhar rota nova sem ser copiada, o assert de cima pega;
    # se a contagem cair, a montagem mudou e este piso precisa ser revisado).
    assert inspecionadas == 82


def test_copia_nao_inventa_nem_perde_rotas():
    rotas_origem = [
        _chave(o)
        for r in _FONTES
        for o in r.routes
        if getattr(o, "path", None) is not None
        and not (o.path in _EXCLUIDAS and r is ramos_ferramentas_complementares.router)
    ]
    rotas_copia = [_chave(x) for x in agregador.router.routes if isinstance(x, APIRoute)]
    # Mesmo multiset de (path, methods): a cópia não cria rota extra nem
    # esquece rota de origem — paridade do snapshot de rotas por construção.
    assert sorted(rotas_copia) == sorted(rotas_origem)


def test_tags_da_copia_nao_duplicam():
    # A regressão concreta da Task 23: TODAS as cópias saíam com a mesma tag
    # repetida (router default do agregador + tags da origem já contendo o
    # default do sub-router de origem).
    for rota in agregador.router.routes:
        tags = getattr(rota, "tags", None) or []
        assert len(tags) == len(set(tags)), f"tags duplicadas em {rota.path}: {tags}"
