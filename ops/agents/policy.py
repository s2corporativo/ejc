from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_FRAGMENTOS_BLOQUEADOS = (
    "git push",
    "force push",
    "git reset --hard",
    "git clean -fd",
    "rm -rf",
    "docker compose down -v",
    "docker volume rm",
    "dropdb",
    "alembic downgrade base",
    "prisma migrate reset",
    "drop database",
    "drop schema",
    "--dangerously-skip-permissions",
    "/opt/ejc",
    "/opt/verdelimp-erp",
)

_RAIZES_REPOSITORIO_PRODUCAO = (
    Path("/opt/ejc"),
    Path("/srv/ejc"),
    Path("/var/www/ejc"),
)

_PADROES_SEGREDO = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)

_ARQUIVOS_SENSIVEIS = {
    ".env",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}

_SUFIXOS_SENSIVEIS = (".pem", ".key", ".p12", ".pfx")

_INDICADORES_REVISAO_SEGURANCA = (
    "autenticação",
    "autenticacao",
    "authentication",
    "autorização",
    "autorizacao",
    "authorization",
    "rbac",
    "permiss",
    "upload",
    "ci/cd",
    "workflow",
    "woodpecker",
    "github actions",
    "dependência",
    "dependencia",
    "dependency",
    "requirements",
    "docker",
    "nginx",
    "compose",
    "middleware",
    "backend/app/core",
    "ai_gateway",
    "pii",
    "segredo",
    "secret",
    "migration",
    "alembic",
    "produção",
    "producao",
    "production",
)


@dataclass(frozen=True, slots=True)
class DecisaoPolitica:
    """Resultado imutável de uma decisão determinística da política operacional."""

    permitido: bool
    motivo: str


def avaliar_tarefa(tarefa: str) -> DecisaoPolitica:
    """Bloqueia pedidos que solicitem explicitamente ações protegidas ou destrutivas."""
    normalizada = " ".join(tarefa.lower().split())
    for fragmento in _FRAGMENTOS_BLOQUEADOS:
        if fragmento in normalizada:
            return DecisaoPolitica(
                permitido=False,
                motivo=f"ação de manutenção bloqueada: {fragmento}",
            )
    return DecisaoPolitica(
        permitido=True,
        motivo="tarefa aceita pela política determinística",
    )


def contem_segredo_provavel(texto: str) -> bool:
    """Detecta formatos de credenciais com alta confiança antes de devolver a saída do agente."""
    return any(padrao.search(texto) is not None for padrao in _PADROES_SEGREDO)


def caminho_sensivel_repositorio(caminho: str) -> bool:
    """Exclui do sandbox arquivos rastreados que provavelmente contenham segredos."""
    normalizado = caminho.replace("\\", "/").lower()
    nome = normalizado.rsplit("/", 1)[-1]

    if nome in _ARQUIVOS_SENSIVEIS:
        return True
    if nome.startswith(".env.") and not nome.endswith(".example"):
        return True
    return nome.endswith(_SUFIXOS_SENSIVEIS)


def caminho_checkout_producao(caminho: Path) -> bool:
    """Reconhece checkout de produção pelo caminho real, inclusive subdiretórios e symlinks."""
    resolvido = caminho.expanduser().resolve()
    for raiz in _RAIZES_REPOSITORIO_PRODUCAO:
        raiz_resolvida = raiz.resolve()
        if resolvido == raiz_resolvida or raiz_resolvida in resolvido.parents:
            return True
    return False


def requer_revisao_seguranca(tarefa: str) -> bool:
    """Exige handoff de segurança quando a tarefa toca áreas sensíveis do EJC."""
    normalizada = " ".join(tarefa.lower().split())
    return any(indicador in normalizada for indicador in _INDICADORES_REVISAO_SEGURANCA)
