#!/usr/bin/env python3
"""Atestação externa do gold set jurídico do EJC.

O corpus versionado consegue provar estrutura e proveniência DECLARADA, mas não
prova que uma pessoa realmente revisou o gabarito: quem altera a branch também
consegue editar nomes e datas no próprio JSONL.

Este módulo valida uma decisão independente da branch usando Ed25519:

- manifesto de atestação fica fora do repositório do corpus;
- chave PÚBLICA de verificação também vem de fonte externa/protegida;
- chave PRIVADA nunca entra no EJC, no CI da branch ou neste código;
- assinatura vincula o HEAD Git e o SHA-256 determinístico do corpus exatos.

A verificação deve ser executada por um gate protegido usando esta implementação
já confiável (por exemplo, da `main`/imagem pinada), e não por código modificado
no mesmo PR que apresenta o corpus. Sem atestação, chave pública, HEAD exato ou
assinatura válida, o comando falha fechado.

Isto comprova que existiu uma decisão externa à branch. Não substitui a revisão
jurídica material nem cria qualquer gabarito automaticamente.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA_VERSION = 1
SCOPE = "ejc-legal-gold"
ENV_HEAD = "EJC_GOLD_HEAD_SHA"
ENV_ATTESTATION_FILE = "EJC_GOLD_ATTESTATION_FILE"
ENV_PUBLIC_KEY_FILE = "EJC_GOLD_ATTESTATION_PUBLIC_KEY_FILE"
_SHA_GIT = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
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


def _linha_eh_candidato(linha: str) -> bool:
    """Linha de gold set ainda não revisada por pessoa (gabarito de treino/IA)."""
    try:
        obj = json.loads(linha)
    except (json.JSONDecodeError, ValueError):
        return False  # linha não-JSON não pode ser descartada por heurística
    if not isinstance(obj, dict):
        return False
    if obj.get("ficticio") is True:
        return True
    return str(obj.get("status") or "").strip().lower() == "candidato"


def _arquivos_gold_reais(base: Path) -> list[Path]:
    arquivos: list[Path] = []
    for path in sorted(base.glob("gold_set*.jsonl")):
        nome = path.name.lower()
        if any(tag in nome for tag in (".example.", ".synthetic.", ".sintetico.")):
            continue
        if not path.is_file() or not path.read_bytes().strip():
            continue
        # Arquivo 100% candidato (nenhuma linha revisada por pessoa) não entra
        # no corpus atestado — atestar gabarito fictício seria falso atestado.
        linhas = [
            ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
        if linhas and all(_linha_eh_candidato(ln) for ln in linhas):
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
    """Representação canônica que a ferramenta humana externa deve assinar."""
    return json.dumps(
        _payload_assinado(manifesto),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


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


def _raiz_git_do_corpus(corpus_dir: Path) -> Path | None:
    """Localiza a raiz Git do checkout que contém o corpus (se houver).

    Manifesto e chave NUNCA podem vir desse checkout — quem controla a branch
    do corpus controla os arquivos dele; a atestação tem que ser externa.
    """
    atual = corpus_dir.resolve()
    for candidato in [atual, *atual.parents]:
        if (candidato / ".git").exists():
            return candidato
    return None


def _fora_do_repositorio(path: Path, repo_root: Path, rotulo: str) -> None:
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return
    raise GoldAttestationError(
        f"{rotulo} deve ser externo ao repositório/branch do corpus"
    )


def _carregar_chave_publica(path: Path) -> Ed25519PublicKey:
    try:
        chave = serialization.load_pem_public_key(path.read_bytes())
    except Exception as exc:
        raise GoldAttestationError("chave pública Ed25519 inválida") from exc
    if not isinstance(chave, Ed25519PublicKey):
        raise GoldAttestationError("chave pública precisa ser Ed25519")
    return chave


def _decodificar_assinatura(valor: Any) -> bytes:
    raw = str(valor or "").strip()
    if not raw:
        raise GoldAttestationError("assinatura Ed25519 ausente")
    try:
        assinatura = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise GoldAttestationError("assinatura Ed25519 não é Base64 válida") from exc
    if len(assinatura) != 64:
        raise GoldAttestationError("assinatura Ed25519 deve ter 64 bytes")
    return assinatura


def validar_atestacao(
    *,
    corpus_dir: str | os.PathLike[str],
    attestation_file: str | os.PathLike[str],
    public_key_file: str | os.PathLike[str],
    head_sha: str,
    repo_root: str | os.PathLike[str],
) -> AttestationResult:
    head = str(head_sha or "").strip().lower()
    if not _SHA_GIT.fullmatch(head):
        raise GoldAttestationError("HEAD Git ausente ou inválido")

    repo = Path(repo_root).resolve()
    att_path = Path(attestation_file).resolve()
    key_path = Path(public_key_file).resolve()
    if not att_path.is_file():
        raise GoldAttestationError("arquivo externo de atestação não encontrado")
    if not key_path.is_file():
        raise GoldAttestationError("arquivo externo de chave pública não encontrado")
    _fora_do_repositorio(att_path, repo, "arquivo de atestação")
    _fora_do_repositorio(key_path, repo, "chave pública de atestação")
    # Mesmo executando a partir de um checkout confiável (main/imagem pinada),
    # os arquivos precisam ser externos ao checkout que contém o corpus —
    # senão um PR consegue apresentar manifesto/chave dentro da própria branch.
    checkout_corpus = _raiz_git_do_corpus(Path(corpus_dir))
    if checkout_corpus is not None and checkout_corpus != repo:
        _fora_do_repositorio(att_path, checkout_corpus, "arquivo de atestação")
        _fora_do_repositorio(key_path, checkout_corpus, "chave pública de atestação")

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

    assinatura = _decodificar_assinatura(manifesto.get("signature_ed25519_base64"))
    chave_publica = _carregar_chave_publica(key_path)
    try:
        chave_publica.verify(assinatura, canonical_payload(manifesto))
    except InvalidSignature as exc:
        raise GoldAttestationError("assinatura Ed25519 não confere") from exc

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
        default=os.getenv(ENV_ATTESTATION_FILE, ""),
    )
    parser.add_argument(
        "--public-key-file",
        default=os.getenv(ENV_PUBLIC_KEY_FILE, ""),
    )
    parser.add_argument(
        "--head-sha",
        default=os.getenv(ENV_HEAD) or os.getenv("CI_COMMIT_SHA") or "",
    )
    args = parser.parse_args()

    try:
        resultado = validar_atestacao(
            corpus_dir=args.corpus_dir,
            attestation_file=args.attestation_file,
            public_key_file=args.public_key_file,
            head_sha=args.head_sha,
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
