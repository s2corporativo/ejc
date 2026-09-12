# ── app/services/ajuizamento ─────────────────────────────────────────────────
# Núcleo de ajuizamento e integração judicial:
#
#   EJC → CanonicalJudicialCase (canonico) → JudicialPreflightValidator
#   (preflight) → SigningProvider (assinatura) → JudicialFilingService
#   (orquestrador) → JudicialConnectorRouter (conectores/roteador) →
#   {PDPJ, PJe-MNI, eproc, DataJud} → ProtocolRegistry (registro_protocolo)
#   → JudicialSyncService (sincronizacao) → EJC.
#
# Regras: nenhum endpoint inventado (host só de perfil cadastrado por admin);
# cada capacidade tem estado explícito SUPPORTED | UNSUPPORTED | CONDITIONAL
# | REQUIRES_AUTHORIZATION; nenhum segredo persiste ou vai a log.
