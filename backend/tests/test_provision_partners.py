from __future__ import annotations

import inspect

import pytest

from seeds import provision_partners as module


def _reader(values: list[str]):
    iterator = iter(values)
    return lambda _prompt: next(iterator)


def test_partner_identities_and_full_access_role_are_explicit():
    assert [(partner.full_name, partner.email) for partner in module.PARTNERS] == [
        ("Clovis Soares", "soares@depaulateixeira.adv.br"),
        ("João Pedro Teixiera", "teixeira@depaulateixeira.adv.br"),
        ("Guilherme Alves de Paula", "depaula@depaulateixeira.adv.br"),
    ]


def test_collects_distinct_strong_passwords_without_echoing():
    values = [
        "Cl0vis@TempForte!",
        "Cl0vis@TempForte!",
        "J0ao@TempForte!",
        "J0ao@TempForte!",
        "Gui1herme@Temp!",
        "Gui1herme@Temp!",
    ]
    result = module.collect_temporary_passwords(
        module.PARTNERS,
        password_reader=_reader(values),
    )
    assert set(result) == {"clovis", "joao", "guilherme"}
    assert len(set(result.values())) == 3


def test_rejects_reused_password():
    repeated = "Senha@Temporaria9"
    values = [
        repeated,
        repeated,
        repeated,
        repeated,
        "Terceira@Senha9",
        "Terceira@Senha9",
    ]
    with pytest.raises(ValueError, match="distinta"):
        module.collect_temporary_passwords(
            module.PARTNERS,
            password_reader=_reader(values),
        )


def test_rejects_weak_password():
    with pytest.raises(ValueError):
        module.collect_temporary_passwords(
            module.PARTNERS[:1],
            password_reader=_reader(["12345678", "12345678"]),
        )


def test_source_contains_no_requested_plaintext_password_or_secret_logging():
    source = inspect.getsource(module)
    assert "35914546" not in source
    assert "print(password" not in source
    assert "hashed_password=get_password_hash" in source
    assert "must_change_password=True" in source
