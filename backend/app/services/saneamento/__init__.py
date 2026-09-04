# ── app/services/saneamento/__init__.py ──────────────────────────────────────
# Módulo de saneamento de base processual. Ver README do pacote de referência
# (ejc-saneamento) e as regras de negócio inegociáveis no PROMPT 1 original:
# sinaliza, nunca decide; DV inválido é erro de digitação, nunca duplicata;
# multi-grau relaciona, jamais funde; conexo é só sugestão; DataJud nunca
# sobrescreve a base interna; nivelSigilo > 0 é tratamento restrito.
from __future__ import annotations
