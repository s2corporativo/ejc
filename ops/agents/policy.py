from __future__ import annotations

import re
from dataclasses import dataclass


_BLOCKED_FRAGMENTS = (
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

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)

_SENSITIVE_FILENAMES = {
    ".env",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}

_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str


def evaluate_task(task: str) -> PolicyDecision:
    """Reject maintenance prompts that explicitly request protected/destructive actions."""
    normalized = " ".join(task.lower().split())
    for fragment in _BLOCKED_FRAGMENTS:
        if fragment in normalized:
            return PolicyDecision(
                allowed=False,
                reason=f"blocked maintenance action: {fragment}",
            )
    return PolicyDecision(allowed=True, reason="task accepted by deterministic policy")


def contains_likely_secret(text: str) -> bool:
    """Detect common high-confidence credential shapes before returning agent output."""
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)


def is_sensitive_repo_path(path: str) -> bool:
    """Exclude likely secret-bearing tracked files from the sandbox materialization."""
    normalized = path.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]

    if name in _SENSITIVE_FILENAMES:
        return True
    if name.startswith(".env.") and not name.endswith(".example"):
        return True
    return name.endswith(_SENSITIVE_SUFFIXES)
