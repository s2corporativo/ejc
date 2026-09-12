# Núcleo de ajuizamento e integração judicial

Fluxo ponta a ponta sem redigitação: **CLIENTE → CASO → PARTES → CLASSE +
ASSUNTO + COMPETÊNCIA → PETIÇÃO + DOCUMENTOS → VALIDAÇÃO → ASSINATURA →
TRIBUNAL/SISTEMA → conector → REVISÃO HUMANA → PROTOCOLO → CNJ + RECIBO →
VINCULAÇÃO AO CASO → SINCRONIZAÇÃO.**

Nenhum cadastro é duplicado: cliente, caso, partes, advogados, documentos e
peças continuam nas tabelas canônicas (`clients`, `cases`, `case_partes`,
`users`, `documents`, `legal_docs`, `procuracoes`). O módulo só acrescenta as
entidades do ato de protocolar.

## Arquitetura

```
EJC → CanonicalJudicialCase (services/ajuizamento/canonico.py)
    → JudicialPreflightValidator (preflight.py)
    → SigningProvider (assinatura.py)
    → JudicialFilingService (orquestrador.py)
    → JudicialConnectorRouter (conectores/roteador.py)
        ├── PDPJConnector   (conectores/pdpj.py)     + PdpjAuthProvider (OIDC/Keycloak)
        ├── PJeMniConnector (conectores/pje_mni.py)  + MniClient {MniRestTransport, MniSoapTransport}
        ├── EprocConnector  (conectores/eproc.py)
        └── DataJudConnector(conectores/datajud.py)  sobre services/datajud_service.py
    → ProtocolRegistry (registro_protocolo.py)
    → JudicialSyncService (sincronizacao.py) → EJC
```

Interface única (`conectores/base.ConectorJudicial`): `validate_target`,
`list_jurisdictions/competences/classes/subjects`, `file_new_case`,
`append_petition`, `read_process`, `read_movements`, `read_notices`,
`download_document`, `receive_callback`, `get_receipt`, `sign`. Operação não
oferecida responde `UNSUPPORTED` **sem I/O**.

Rotas: `/api/ajuizamento/*` (capacidades, perfis, TPU, filings, protocolos) —
todas autenticadas; atos jurídicos exigem advogado+; perfis e carga TPU, admin.
Tabelas: migration `157_ajuizamento_judicial` (`judicial_filings`,
`judicial_filing_transicoes`, `judicial_filing_attempts`, `judicial_protocols`,
`judicial_integration_profiles`, `judicial_sync_events`, `judicial_tpu_itens`).
Auditoria usa o `AuditLog` existente (ações `AJUIZ_*`), com PII/segredo redigidos.

## Máquina de estados

`DRAFT → PREPARING → VALIDATING → (INVALID | READY_FOR_REVIEW) → APPROVED →
SIGNING → READY_TO_SUBMIT → SUBMITTING → (SUBMITTED | CONFIRMED |
REQUIRES_AUTHORIZATION | FAILED) → SYNCING → CONFIRMED`; `CANCELLED` é
terminal. Toda transição grava linha em `judicial_filing_transicoes` (ator +
motivo).

Invariantes:
- `VALIDATING` **nunca** vai direto a `APPROVED` — a revisão humana
  (`READY_FOR_REVIEW → APPROVED`) exige a confirmação literal
  **"REVISAR E PROTOCOLAR"** e a peça aprovada com HITL;
- editar depois de validar volta a `DRAFT` e descarta o preflight;
- aprovar exige `canonico_hash` idêntico ao da validação (dado que mudou
  depois da revisão obriga revalidar);
- protocolar exige aprovação + assinatura + `JUDICIAL_FILING_ENABLED`;
- idempotência: `idempotency_key = sha256(filing.id | nº tentativa |
  canonico_hash)`; repetição de POST devolve o protocolo anterior; após
  `TIMEOUT` o orquestrador consulta `get_receipt` antes de qualquer reenvio e,
  sem meio de verificar, exige confirmação manual.

## Matriz de capacidades

Calculada (não persistida) por conector × tribunal × sistema × versão ×
ambiente × credencial × homologação, em `GET /ajuizamento/capacidades`.
Estados: `SUPPORTED | UNSUPPORTED | CONDITIONAL | REQUIRES_AUTHORIZATION`.

| Conector | Leitura | Protocolo (`file_new_case`) | Observação |
|---|---|---|---|
| **DataJud** | `SUPPORTED` com `DATAJUD_ENABLED` + chave; senão `CONDITIONAL` | `UNSUPPORTED` | Acompanhamento complementar: capa + movimentos públicos. Nunca peticiona, anexa, assina nem vale como intimação. |
| **PJe/MNI** | `CONDITIONAL`/`SUPPORTED` (leitura 2.2.2 pela fila Celery, tribunal em `/processo-eletronico`) | `SUPPORTED` só com perfil homologado + `PJE_MNI_ENABLED` + token; senão `REQUIRES_AUTHORIZATION` | Host/contexto/versão vêm do perfil; versões 2.2.2/2.2.3/3.0.0. |
| **PDPJ-Br** | `REQUIRES_AUTHORIZATION` | `REQUIRES_AUTHORIZATION` | Mapeamento segue os campos documentados de `pet-inicial`; o endpoint de envio por terceiros não é público. `receive_callback` é `SUPPORTED`. |
| **eproc** | `CONDITIONAL` por convênio | `REQUIRES_AUTHORIZATION` | Nenhum endpoint presumido: só com `base_url` + documentação informadas pelo tribunal no perfil. |

Escrita só vira `SUPPORTED` com **os quatro selos** do perfil: `authorized` +
`homologated_at` + `production_endpoint_verified` + `credentials_valid` — e
credencial presente. Assinatura: `registro_externo`/`pje_office` são
`SUPPORTED` (o EJC registra a evidência da assinatura ICP-Brasil feita na
estação, conferindo o SHA-256); `a1`, `a3_pkcs11` e `psc_nuvem` são
`REQUIRES_AUTHORIZATION` — chave privada nunca entra no servidor.

## Checklist de homologação por tribunal

Preencher em **Administrar → Perfis de tribunal** (`/ajuizamento/perfis`):

1. `tribunal_code`, `segment`, `degree`, `system`, `environment`;
2. `base_url` (https, sem IP privado — validado no backend) e `api_version`;
3. `auth_type` e `client_id_ref`/`certificate_ref` — **referência**
   `provider_key:field_key` ao Cofre, nunca o valor;
4. capacidades declaradas pelo tribunal (`filing_supported`,
   `append_petition_supported`, `process_query_supported`, …);
5. `homologation_checklist` (JSON livre: `id_sistema_destino`,
   `campos_obrigatorios`, número do processo de homologação, contatos);
6. selos: `authorized` → `homologated_at` → `production_endpoint_verified` →
   `credentials_valid`.

Sem os quatro selos, o fluxo vai até a revisão e o protocolo é registrado
manualmente (`POST /ajuizamento/filings/{id}/confirmar-manual`), com vínculo
automático ao processo, à peça e à timeline do caso.

## Flags (default OFF)

`JUDICIAL_FILING_ENABLED`, `PDPJ_INTEGRATION_ENABLED` (+`PDPJ_ENVIRONMENT`,
`PDPJ_CLIENT_ID`, `PDPJ_CLIENT_SECRET`), `PJE_MNI_ENABLED`,
`EPROC_INTEGRATION_ENABLED`. Reaproveitadas: `DATAJUD_ENABLED`,
`DATAJUD_SYNC_ENABLED`, `CNJ_SGT_ENABLED` (sync da TPU), `CELERY_ENABLED`.

## Pendências externas

| Órgão / sistema | O que solicitar | Credencial | Documentação | Impacto |
|---|---|---|---|---|
| CNJ — PDPJ-Br | Cadastro de client Keycloak e habilitação do escritório no Portal de Serviços | `client_id` + `client_secret` (client_credentials) | `docs.pdpj.jus.br/servicos-estruturantes/autenticacao-sso/`, `.../portal-servicos/pet-inicial/`; solicitação por `integracaopdpj@cnj.jus.br` | Sem isso o PDPJ fica `REQUIRES_AUTHORIZATION`; o payload já está mapeado, mas o endpoint de envio por terceiros não é público |
| Tribunal (PJe) | Habilitação do MNI Client e do `idSistemaDestino`; homologação | Token SSO com role `invoke-service-endpoint` (+ credencial MNI de leitura) | `docs.pje.jus.br/servicos-auxiliares/servico-mni-client/` | Sem isso não há `entregarManifestacaoProcessual` |
| Tribunais eproc | Convênio/contrato de integração e contrato técnico do serviço | Definida pelo tribunal (token/certificado) | Fornecida pelo próprio tribunal | Sem isso o eproc permanece `REQUIRES_AUTHORIZATION` |
| CNJ — SGT/TPU | Nada (serviço público); basta `CNJ_SGT_ENABLED=true` | — | `www.cnj.jus.br/sgt/` | Cache TPU vazio → a validação avisa que o código não foi verificado |
| ICP-Brasil / PSC | Certificado A1/A3 ou contrato com prestadora credenciada | Fica com o advogado, fora do EJC | — | Assinatura na estação + registro da evidência no EJC |

## Limites deliberados

- Sem Selenium/Playwright/scraping ou automação de tela em qualquer ponto.
- DataJud jamais é usado para peticionar, anexar, assinar, tratar sigilo ou
  como intimação válida.
- Nenhum endpoint, WSDL, `client_id` ou token é inventado: o que não estiver
  documentado ou no perfil do tribunal responde `REQUIRES_AUTHORIZATION`.
