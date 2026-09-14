import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.eval.gold_attestation import (
    GoldAttestationError,
    SCOPE,
    SCHEMA_VERSION,
    canonical_payload,
    digest_corpus,
    validar_atestacao,
)


HEAD = "a" * 40


def _cenario(tmp_path: Path):
    repo = tmp_path / "repo"
    corpus = repo / "backend" / "app" / "eval"
    corpus.mkdir(parents=True)
    gold = corpus / "gold_set_real.jsonl"
    gold.write_text('{"id":"real-1","ficticio":false}\n', encoding="utf-8")

    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    public_path = tmp_path / "gold-public.pem"
    public_path.write_bytes(
        public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    digest, _ = digest_corpus(corpus)
    manifesto = {
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "head_sha": HEAD,
        "corpus_sha256": digest,
        "attested_by": "advogado-revisor",
        "attested_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }
    manifesto["signature_ed25519_base64"] = base64.b64encode(
        private.sign(canonical_payload(manifesto))
    ).decode("ascii")

    attestation = tmp_path / "gold-attestation.json"
    attestation.write_text(json.dumps(manifesto), encoding="utf-8")
    return repo, corpus, gold, public_path, attestation, manifesto


def test_atestacao_valida_vincula_head_e_corpus_exatos(tmp_path):
    repo, corpus, _gold, public_path, attestation, _ = _cenario(tmp_path)

    resultado = validar_atestacao(
        corpus_dir=corpus,
        attestation_file=attestation,
        public_key_file=public_path,
        head_sha=HEAD,
        repo_root=repo,
    )

    assert resultado.head_sha == HEAD
    assert resultado.attested_by == "advogado-revisor"
    assert resultado.files == ("gold_set_real.jsonl",)


def test_atestacao_rejeita_head_diferente(tmp_path):
    repo, corpus, _gold, public_path, attestation, _ = _cenario(tmp_path)
    with pytest.raises(GoldAttestationError, match="HEAD Git exato"):
        validar_atestacao(
            corpus_dir=corpus,
            attestation_file=attestation,
            public_key_file=public_path,
            head_sha="b" * 40,
            repo_root=repo,
        )


def test_atestacao_rejeita_corpus_alterado_depois_da_assinatura(tmp_path):
    repo, corpus, gold, public_path, attestation, _ = _cenario(tmp_path)
    gold.write_text(
        '{"id":"real-1","ficticio":false}\n{"id":"mudou","ficticio":false}\n',
        encoding="utf-8",
    )

    with pytest.raises(GoldAttestationError, match="corpus exato"):
        validar_atestacao(
            corpus_dir=corpus,
            attestation_file=attestation,
            public_key_file=public_path,
            head_sha=HEAD,
            repo_root=repo,
        )


def test_atestacao_rejeita_assinatura_forjada(tmp_path):
    repo, corpus, _gold, public_path, attestation, manifesto = _cenario(tmp_path)
    manifesto["signature_ed25519_base64"] = base64.b64encode(b"x" * 64).decode("ascii")
    attestation.write_text(json.dumps(manifesto), encoding="utf-8")

    with pytest.raises(GoldAttestationError, match="assinatura Ed25519 não confere"):
        validar_atestacao(
            corpus_dir=corpus,
            attestation_file=attestation,
            public_key_file=public_path,
            head_sha=HEAD,
            repo_root=repo,
        )


def test_manifesto_e_chave_publica_devem_ficar_fora_da_branch(tmp_path):
    repo, corpus, _gold, public_path, attestation, manifesto = _cenario(tmp_path)

    att_interno = repo / "attestation.json"
    att_interno.write_text(json.dumps(manifesto), encoding="utf-8")
    with pytest.raises(GoldAttestationError, match="arquivo de atestação deve ser externo"):
        validar_atestacao(
            corpus_dir=corpus,
            attestation_file=att_interno,
            public_key_file=public_path,
            head_sha=HEAD,
            repo_root=repo,
        )

    key_interna = repo / "public.pem"
    key_interna.write_bytes(public_path.read_bytes())
    with pytest.raises(GoldAttestationError, match="chave pública de atestação deve ser externo"):
        validar_atestacao(
            corpus_dir=corpus,
            attestation_file=attestation,
            public_key_file=key_interna,
            head_sha=HEAD,
            repo_root=repo,
        )


def test_exemplos_nao_entram_no_digest_real(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "gold_set_real.jsonl").write_text("real\n", encoding="utf-8")
    digest_antes, arquivos_antes = digest_corpus(corpus)
    (corpus / "gold_set.example.jsonl").write_text("exemplo alterável\n", encoding="utf-8")
    digest_depois, arquivos_depois = digest_corpus(corpus)

    assert digest_depois == digest_antes
    assert arquivos_antes == arquivos_depois == ("gold_set_real.jsonl",)
