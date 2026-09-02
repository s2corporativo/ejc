#!/usr/bin/env python3
"""Atestação externa do gold set jurídico do EJC.

O arquivo JSONL do corpus consegue provar estrutura/proveniência declarada, mas
não consegue provar que uma pessoa realmente revisou o gabarito: um agente com
acesso à branch também consegue editar nomes e datas no próprio corpus.

Este módulo fecha essa classe de falso positivo sem criar dados jurídicos. A
atestação precisa existir FORA do repositório e ser autenticada por HMAC com uma
chave fornecida pelo ambiente de CI/operação. O segredo nunca é lido de arquivo
versionado e nunca é impresso.

A assinatura vincula exatamente:
- HEAD Git;
- SHA-256 determinístico do corpus real;
- identidade declarada do atestador;
- instante da atestação;
- escopo/schema do contrato.

Sem arquivo externo, chave, HEAD exato ou assinatura válida, a verificação falha
fechado. Este mecanismo comprova a existência de uma decisão externa à branch;
a correção jurídica material continua sendo responsabilidade humana.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SCOPE = "ejc-legal-gold"
ENV_KEY = "EJC_GOLD_ATTESTATION_KEY"
ENV_HEAD = "EJC_GOLD_HEAD_SHA"
_SHA_GIT = re.compile(r"^[0-9a-fA-F]{40,64}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class GoldAttestationError(ValueError):
    """Atestação ausente, inconsistente ou não autenticada."""


@dataclass(frozen=True)
class AttestationResult:
    head_sha: str
    corpus_sha256: str
    attested_by: str
    attested_at: str
    files: tuple[str, ...]


def _arquivos_gold_reais(base: Path) -> list[Path]:
    arquivos: list[Path] = []
    for path in sorted(base.glob("gold_set*.jsonl")):
        nome = path.name.lower()
        if any(tag in nome for tag in (".example.", ".synthetic.", ".sintetico.")):
            continue
        if not path.is_file() or not path.read_bytes().strip():
            continue
        arquivos.append(path)
    return arquivos


def digest_corpus(base: str | os.PathLike[str]) -> tuple[str, tuple[str, ...]]:
    """Hash determinístico do nome + bytes de cada gold set real não vazio."""
    raiz = Path(base).resolve()
    arquivos = _arquivos_gold_reais(raiz)
    if not arquivos:
        raise GoldAttestationError("nenhum arquivo gold real não vazio para atestar")

    h = hashlib.sha256()
    nomes: list[str] = []
    for path in arquivos:
        rel = path.relative_to(raiz).as_posix()
        nomes.append(rel)
        dados = path.read_bytes()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(str(len(dados)).encode("ascii"))
        h.update(b"\0")
        h.update(dados)
        h.update(b"\0")
    return h.hexdigest(), tuple(nomes)


def _payload_assinado(manifesto: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": manifesto.get("schema_version"),
        "scope": manifesto.get("scope"),
        "head_sha": manifesto.get("head_sha"),
        "corpus_sha256": manifesto.get("corpus_sha256"),
        "attested_by": manifesto.get("attested_by"),
        "attested_at": manifesto.get("attested_at"),
    }


def canonical_payload(manifesto: dict[str, Any]) -> bytes:
    """Representação canônica usada pelo verificador e pelo processo de assinatura."""
    return json.dumps(
        _payload_assinado(manifesto),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def assinatura_esperada(manifesto: dict[str, Any], chave: str) -> str:
    """Calcula HMAC; utilidade pública para testes/ferramenta humana externa."""
    if len(chave.encode("utf-8")) < 32:
        raise GoldAttestationError("chave de atestação deve ter ao menos 32 bytes")
    return hmac.new(
        chave.encode("utf-8"), canonical_payload(manifesto), hashlib.sha256
    ).hexdigest()


def _data_atestacao(valor: Any) -> str:
    raw = str(valor or "").strip()
    if not raw:
        raise GoldAttestationError("attested_at é obrigatório")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GoldAttestationError("attested_at deve ser ISO-8601") from exc
    if parsed.tzinfo is None:
        raise GoldAttestationError("attested_at deve conter timezone")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise GoldAttestationError("attested_at não pode estar no futuro")
    return raw


def _fora_do_repositorio(path: Path, repo_root: Path) -> None:
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return
    raise GoldAttestationError(
        "arquivo de atestação deve ser externo ao repositório/branch do corpus"
    )


def validar_atestacao(
    *,
    corpus_dir: str | os.PathLike[str],
    attestation_file: str | os.PathLike[str],
    head_sha: str,
    chave: str,
    repo_root: str | os.PathLike[str],
) -> AttestationResult:
    head = str(head_sha or "").strip().lower()
    if not _SHA_GIT.fullmatch(head):
        raise GoldAttestationError("HEAD Git ausente ou inválido")

    att_path = Path(attestation_file).resolve()
    if not att_path.is_file():
        raise GoldAttestationError("arquivo externo de atestação não encontrado")
    _fora_do_repositorio(att_path, Path(repo_root))

    try:
        manifesto = json.loads(att_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoldAttestationError("manifesto de atestação inválido") from exc
    if not isinstance(manifesto, dict):
        raise GoldAttestationError("manifesto de atestação deve ser objeto JSON")

    if manifesto.get("schema_version") != SCHEMA_VERSION:
        raise GoldAttestationError("schema_version de atestação não suportado")
    if manifesto.get("scope") != SCOPE:
        raise GoldAttestationError("scope de atestação inválido")

    manifest_head = str(manifesto.get("head_sha") or "").strip().lower()
    if manifest_head != head:
        raise GoldAttestationError("atestação não corresponde ao HEAD Git exato")

    corpus_sha, files = digest_corpus(corpus_dir)
    manifest_corpus = str(manifesto.get("corpus_sha256") or "").strip().lower()
    if not _SHA256.fullmatch(manifest_corpus) or manifest_corpus != corpus_sha:
        raise GoldAttestationError("atestação não corresponde ao corpus exato")

    attested_by = str(manifesto.get("attested_by") or "").strip()
    if len(attested_by) < 3:
        raise GoldAttestationError("attested_by é obrigatório")
    attested_at = _data_atestacao(manifesto.get("attested_at"))

    assinatura = str(manifesto.get("signature_hmac_sha256") or "").strip().lower()
    if not _SHA256.fullmatch(assinatura):
        raise GoldAttestationError("assinatura HMAC ausente ou inválida")
    esperada = assinatura_esperada(manifesto, chave)
    if not hmac.compare_digest(assinatura, esperada):
        raise GoldAttestationError("assinatura HMAC não confere")

    return AttestationResult(
        head_sha=head,
        corpus_sha256=corpus_sha,
        attested_by=attested_by,
        attested_at=attested_at,
        files=files,
    )


def main() -> None:
    aqui = Path(__file__).resolve()
    repo_root = aqui.parents[3]
    parser = argparse.ArgumentParser(
        description="Valida atestação humana externa vinculada ao gold set e HEAD exatos"
    )
    parser.add_argument("--corpus-dir", default=str(aqui.parent))
    parser.add_argument(
        "--attestation-file",
        default=os.getenv("EJC_GOLD_ATTESTATION_FILE", ""),
    )
    parser.add_argument(
        "--head-sha",
        default=os.getenv(ENV_HEAD) or os.getenv("CI_COMMIT_SHA") or "",
    )
    args = parser.parse_args()

    chave = os.getenv(ENV_KEY, "")
    try:
        resultado = validar_atestacao(
            corpus_dir=args.corpus_dir,
            attestation_file=args.attestation_file,
            head_sha=args.head_sha,
            chave=chave,
            repo_root=repo_root,
        )
    except GoldAttestationError as exc:
        print(f"GOLD ATTESTATION: BLOQUEADO — {exc}")
        raise SystemExit(1) from exc

    print(
        "GOLD ATTESTATION: OK — "
        f"head={resultado.head_sha[:12]} corpus={resultado.corpus_sha256[:12]} "
        f"atestador={resultado.attested_by} arquivos={len(resultado.files)}"
    )


if __name__ == "__main__":
    main()
