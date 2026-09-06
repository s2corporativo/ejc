"""Guardas de higiene do código — impedem a volta do que a limpeza removeu.

Nascem da varredura da Issue #1543: dependência declarada sem nenhum
``import`` e módulo de ``app/`` que ninguém importa. São verificações
NATIVAS (sem knip/deptry/vulture) para não reintroduzir peso de
ferramenta só para medir peso.
"""
from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"

# Dependências legitimamente sem ``import`` no código-fonte: entrypoint de
# processo, plugin de ferramenta, driver resolvido por URL ou dependência
# transitiva pinada por segurança. Cada entrada precisa de justificativa.
DEPS_SEM_IMPORT_DIRETO = {
    "uvicorn": "servidor ASGI — entrypoint de processo (Dockerfile/compose)",
    "gunicorn": "gerenciador de workers — entrypoint de processo",
    "ruff": "linter — CLI, nunca importado",
    "pytest-asyncio": "plugin do pytest — ativado por pytest.ini",
    "pytest-cov": "plugin do pytest — ativado por linha de comando",
    "python-multipart": "FastAPI usa para multipart/form-data (upload)",
    "email-validator": "pydantic EmailStr resolve em runtime",
    "python-magic-bin": "variante Windows do python-magic (mesmo módulo)",
    "pydyf": "dependência do weasyprint — pin explícito de segurança",
    "greenlet": "ponte sync/async do SQLAlchemy — resolvida em runtime",
    "asyncpg": "driver do PostgreSQL — resolvido pela DATABASE_URL",
    "psycopg2-binary": "driver síncrono do Alembic — resolvido pela URL",
    "aiosqlite": "driver de testes — resolvido pela URL",
    "jinja2": "transitiva de fastapi/starlette — pin explícito de segurança",
    "lxml": "transitiva de zeep/python-docx/beautifulsoup4 — pin de segurança",
}

# Módulo vivo que ainda não tem quem o chame, com dono e prazo registrados.
MODULOS_SEM_IMPORT_CONHECIDOS = {
    "app/tasks/rescan_tasks.py": (
        "backfill SHA-256 do épico #1019 (Onda C): as tabelas já existem "
        "(migration 142), falta a rota de disparo — rastreado na Issue #1544"
    ),
}


def _fontes() -> str:
    partes: list[str] = []
    bases = (APP, RAIZ / "scripts", RAIZ / "alembic", RAIZ / "seeds",
             RAIZ / "tests", RAIZ.parent / "scripts")
    for base in bases:
        if not base.is_dir():
            continue
        for arquivo in base.rglob("*.py"):
            partes.append(arquivo.read_text(encoding="utf-8", errors="ignore"))
    for extra in ("Dockerfile", "entrypoint.sh", "pytest.ini", "alembic.ini"):
        caminho = RAIZ / extra
        if caminho.is_file():
            partes.append(caminho.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(partes)


def _modulos_da_distribuicao(dist: str) -> set[str]:
    """Módulos de topo que a distribuição instala (fonte: metadata)."""
    try:
        arquivos = metadata.distribution(dist).files or []
    except metadata.PackageNotFoundError:
        return set()
    topo: set[str] = set()
    for arquivo in arquivos:
        partes = Path(str(arquivo)).parts
        if not partes or partes[0].endswith((".dist-info", ".egg-info")):
            continue
        nome = partes[0]
        if nome.endswith(".py"):
            nome = nome[:-3]
        elif "." in nome:
            continue
        if nome.isidentifier():
            topo.add(nome)
    return topo


def test_toda_dependencia_declarada_tem_import():
    fontes = _fontes()
    requisitos = []
    for linha in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        requisitos.append(re.split(r"[<>=!~\[; ]", linha)[0])

    orfas: list[str] = []
    for dist in requisitos:
        if dist in DEPS_SEM_IMPORT_DIRETO:
            continue
        modulos = _modulos_da_distribuicao(dist)
        if not modulos:  # não instalada neste ambiente — nada a afirmar
            continue
        if not any(
            re.search(rf"^\s*(?:import|from)\s+{re.escape(m)}\b", fontes, re.M)
            for m in modulos
        ):
            orfas.append(f"{dist} (módulos: {', '.join(sorted(modulos))})")

    assert not orfas, (
        "Dependência em requirements.txt sem nenhum import no backend:\n  "
        + "\n  ".join(sorted(orfas))
        + "\n\nRemova a dependência ou registre a justificativa em "
        "DEPS_SEM_IMPORT_DIRETO."
    )


def test_todo_modulo_de_app_e_importado():
    fontes = _fontes()
    referencias: set[str] = set(re.findall(r"\bapp(?:\.[A-Za-z_][\w]*)+", fontes))
    for pacote, nomes in re.findall(
        r"^\s*from\s+(app(?:\.[\w]+)*)\s+import\s+([^\n(]+|\([^)]*\))", fontes, re.M
    ):
        for nome in nomes.replace("(", "").replace(")", "").split(","):
            nome = nome.strip().split(" as ")[0].strip()
            if nome:
                referencias.add(f"{pacote}.{nome}")

    # ``from .modulo import X`` / ``from ..pacote.modulo import X``
    relativos: set[str] = set()
    for alvo in re.findall(r"^\s*from\s+\.+([\w.]*)\s+import\s", fontes, re.M):
        if alvo:
            relativos.add(alvo.split(".")[-1])

    orfaos: list[str] = []
    for arquivo in APP.rglob("*.py"):
        if arquivo.name in ("__init__.py", "main.py"):
            continue
        modulo = arquivo.relative_to(RAIZ).with_suffix("")
        pontilhado = ".".join(modulo.parts)
        if pontilhado in referencias or arquivo.stem in relativos:
            continue
        # re-export pelo __init__ do pacote também conta como uso
        init = arquivo.parent / "__init__.py"
        if init.is_file() and re.search(
            rf"\b{re.escape(arquivo.stem)}\b",
            init.read_text(encoding="utf-8", errors="ignore"),
        ):
            continue
        relativo = arquivo.relative_to(RAIZ).as_posix()
        if relativo in MODULOS_SEM_IMPORT_CONHECIDOS:
            continue
        orfaos.append(relativo)

    assert not orfaos, (
        "Módulo em app/ que nenhum import alcança (código morto):\n  "
        + "\n  ".join(sorted(orfaos))
    )
