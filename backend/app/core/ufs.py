# ── app/core/ufs.py ──────────────────────────────────────────────────────────
# Unidades federativas do Brasil — 26 estados + Distrito Federal (CF/1988,
# art. 1º; siglas conforme IBGE/DTB). Lista fechada e estável: serve de
# validação para qualquer campo "UF" do sistema (OAB, endereço, tribunal).
#
# Existe porque a sigla da UF é DADO CRÍTICO na captura de intimações: uma UF
# errada monitora a inscrição de outro advogado no país, e uma UF ausente faz
# a captura pular o advogado em silêncio.
from __future__ import annotations

UFS_BRASIL: frozenset[str] = frozenset({
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
})

# Ordem de exibição (alfabética) para selects e relatórios.
UFS_BRASIL_ORDENADAS: tuple[str, ...] = tuple(sorted(UFS_BRASIL))
