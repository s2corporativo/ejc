"""Retry com backoff para erro HTTP TRANSIENTE (429/529) antes do fallback lateral (IA-006).

Antes, qualquer exceção de provider — rate limit passageiro incluído — caía
IMEDIATAMENTE para o próximo provedor da cadeia. `_chamar_com_retry_transiente`
insiste no MESMO provider, com backoff exponencial, só para os status que
realmente costumam se resolver sozinhos em segundos (429, 529); qualquer outro
erro continua caindo para o próximo provider na primeira tentativa, como antes.
"""

from __future__ import annotations

import pytest

from app.services.ai_gateway import (
    _ProviderPulado,
    _chamar_com_retry_transiente,
)


class _ErroHttp(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


@pytest.fixture
def esperas(monkeypatch):
    """Substitui asyncio.sleep por um dublê que registra a duração pedida em
    vez de dormir de verdade — os testes de backoff rodam em milissegundos."""
    registradas: list[float] = []

    async def _fake_sleep(segundos):
        registradas.append(segundos)

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)
    return registradas


async def test_sucesso_na_primeira_tentativa_nao_dorme(esperas):
    async def _ok():
        return "resposta"

    resultado = await _chamar_com_retry_transiente(_ok, tentativas=2, backoff_base=0.5)
    assert resultado == "resposta"
    assert esperas == []


async def test_429_transiente_tenta_de_novo_e_sucede(esperas):
    """O caso central: 429 na 1ª chamada, sucesso na 2ª — sem cair para outro
    provider (quem decide isso é o CHAMADOR de _chamar_com_retry_transiente,
    que só vê o resultado final, não as tentativas internas)."""
    chamadas = {"n": 0}

    async def _falha_uma_vez():
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise _ErroHttp(429)
        return "resposta apos retry"

    resultado = await _chamar_com_retry_transiente(_falha_uma_vez, tentativas=2, backoff_base=0.5)
    assert resultado == "resposta apos retry"
    assert chamadas["n"] == 2
    assert esperas == [0.5]  # backoff da 1ª tentativa


async def test_529_overloaded_tambem_e_transiente(esperas):
    chamadas = {"n": 0}

    async def _falha_uma_vez():
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise _ErroHttp(529)
        return "ok"

    resultado = await _chamar_com_retry_transiente(_falha_uma_vez, tentativas=2, backoff_base=0.1)
    assert resultado == "ok"
    assert chamadas["n"] == 2


async def test_esgotar_tentativas_propaga_o_ultimo_erro(esperas):
    chamadas = {"n": 0}

    async def _sempre_429():
        chamadas["n"] += 1
        raise _ErroHttp(429)

    with pytest.raises(_ErroHttp) as exc:
        await _chamar_com_retry_transiente(_sempre_429, tentativas=2, backoff_base=0.1)
    assert exc.value.status_code == 429
    # tentativa inicial + 2 retries = 3 chamadas.
    assert chamadas["n"] == 3


async def test_erro_nao_transiente_nao_tenta_de_novo(esperas):
    """400/401/500 continuam caindo IMEDIATAMENTE para o próximo provider —
    sem retry, sem espera, sem mudança de comportamento para estes casos."""
    chamadas = {"n": 0}

    async def _erro_permanente():
        chamadas["n"] += 1
        raise _ErroHttp(401)

    with pytest.raises(_ErroHttp) as exc:
        await _chamar_com_retry_transiente(_erro_permanente, tentativas=2, backoff_base=0.5)
    assert exc.value.status_code == 401
    assert chamadas["n"] == 1  # nenhuma segunda tentativa
    assert esperas == []


async def test_provider_pulado_por_pii_nao_e_retentado(esperas):
    """Bloqueio de PII (LGPD) não é falha de rede — não faz sentido re-tentar
    o MESMO provider, e ele nunca vai deixar de estar "pulado" numa 2ª chamada
    idêntica. Propaga na primeira tentativa para o fallback lateral tratar."""
    chamadas = {"n": 0}

    async def _bloqueado():
        chamadas["n"] += 1
        raise _ProviderPulado(["CPF"])

    with pytest.raises(_ProviderPulado):
        await _chamar_com_retry_transiente(_bloqueado, tentativas=2, backoff_base=0.5)
    assert chamadas["n"] == 1
    assert esperas == []


async def test_tentativas_zero_desliga_o_retry(esperas):
    """`tentativas=0` é o kill-switch operacional: comportamento idêntico ao
    ponto anterior a esta correção."""
    chamadas = {"n": 0}

    async def _sempre_429():
        chamadas["n"] += 1
        raise _ErroHttp(429)

    with pytest.raises(_ErroHttp):
        await _chamar_com_retry_transiente(_sempre_429, tentativas=0, backoff_base=0.5)
    assert chamadas["n"] == 1
    assert esperas == []


async def test_backoff_e_exponencial(esperas):
    async def _sempre_429():
        raise _ErroHttp(429)

    with pytest.raises(_ErroHttp):
        await _chamar_com_retry_transiente(_sempre_429, tentativas=3, backoff_base=0.5)
    assert esperas == [0.5, 1.0, 2.0]
