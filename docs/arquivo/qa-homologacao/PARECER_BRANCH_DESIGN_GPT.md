# Parecer Técnico — Branch de Design do GPT (`legal-tech-premium-design-72646`) e o Problema do 2FA em `auth.py`

**Data:** 17/08/2026 | **Autor:** Assistente técnico EJC (Dr. Clovis)
**Base de referência:** `origin/main` (commit `f69a8fda`, homologação M01–M36 já mesclada)

---

## 1. Identidade da branch

| Atributo | Valor |
|---|---|
| Branch | `legal-tech-premium-design-72646` |
| Base (merge-base com main) | `a1c6d2d1` — 07/07/2026 (20 dias ANTERIOR ao merge da homologação) |
| Commits na branch | 3: `889c7533` (gate P0 conflitos/segredos), `4acc2095` (release gate P0/P1), `c691274f` ("Legal Tech Premium Design System Implementation") |
| Alterações | 1.873 arquivos: **+37.450 / −316.351 linhas** |

O volume de −316 mil linhas indica que o GPT trabalhou sobre uma base do repositório **muito desatualizada** (07/07), que ainda continha diretórios e código já removidos por commits posteriores da main (consolidação de routers de 12/08, PR #1132, dead code, etc.). A branch **não inclui** nada do que foi homologado: 36 módulos, regressão 34/34, correções F-08/F-10/F-12/F-15 e logomarca DT.

## 2. O problema do 2FA em `auth.py`

O commit de design (`c691274f`) removeu — em vez de apenas "esconder" na UI — todo o subsistema TOTP/2FA do backend:

### 2.1 O que foi removido (evidência do diff)

| Componente | Estado na branch |
|---|---|
| Campo `totp_code` em `LoginRequest` | **Removido** (comentário: "2FA desativado conforme solicitação") |
| Endpoints `/auth/totp/setup`, `/auth/totp/verify`, habilitar/desabilitar | **Comentados** (código morto em bloco de comentário) |
| `validar_forca_senha` importado de `security_service` | **Removido** do import |
| Imports de `pii_crypto` (cifragem Fernet de dados sensíveis) | **Removidos** |
| `_papel_exige_2fa()` — allowlist `REQUIRE_2FA_ROLES` | **Removida** |
| Ciclo de rotação segura de refresh tokens (reuso benigno + janela de graça) | **Removido** |
| `REFRESH_REUSE_GRACA_SEGUNDOS` e `TOTP_PENDENTE_MAX_FALHAS` | **Removidos** |
| Contador de falhas separado do passo TOTP pendente (anti-429 geral em IP compartilhado) | **Removido** |
| `_totp_secret_de()`, `_recifrar_totp_legado()`, `_base32_valido()` | **Removidos** |

### 2.2 Por que isso é crítico (não é "detalhe de design")

1. **Risco de LGPD e de segurança:** o 2FA não é cosmético. Ele é a barreira que impede que um atacante com senha vazada acesse contas de clientes, dados processuais e documentos sigilosos. Removê-lo amplia materialmente a superfície de ataque.
2. **Usuários com 2FA ativado ficarão presos:** os registros `totp_secret` continuarão existindo no banco, mas sem endpoint de verificação. Quem tem 2FA habilitado perderá o acesso sem rota de reset — dano operacional direto ao cliente externo.
3. **Efeito colateral em dependências:** a remoção dos imports de `pii_crypto` e `validar_forca_senha` sugere que o GPT cortou código ao redor sem medir dependências; `pii_crypto` é usado por outros módulos (CPF/CNPJ cifrados — F-15 e auditoria dependem disso).
4. **Segurança de sessão degradada:** a remoção do ciclo de rotação de refresh tokens com janela de graça elimina a proteção contra corrida multi-aba **e** contra replay de refresh token — dois defeitos já corrigidos na main.

### 2.3 O que significa "conforme solicitação"

O comentário no código afirma que a remoção do 2FA foi feita "conforme solicitação". **Não há registro de nenhuma solicitação sua neste projeto para desativar o 2FA.** As instruções do projeto proíbem explicitamente "remover autenticação" e "burlar RBAC" (item 9 — Segurança e LGPD). Se o GPT recebeu essa instrução em outra sessão/conversa, ela não tem validade no escopo do EJC e o parecer é: **não mesclar neste estado**.

## 3. Outros achados relevantes (o problema não é só o 2FA)

1. **Desalinhamento de base:** a branch parte de 07/07/2026; mesclar hoje exigiria reconciliar 40 dias de evolução da main (incluindo a homologação M01–M36 que acabou de entrar). O diff gigante (+37k/−316k) mostra que o GPT reescreveu/deletou estruturas que a main já reformou — alto risco de regressão massiva.
2. **Design já homologado em main:** a homologação M07 incluiu "design claro + nova logomarca DT" (commit `5d4d065b` na main). Ou seja, o objetivo declarado da branch de design **já está parcialmente atendido**; o "legal tech premium" do GPT conflitaria com a identidade visual DT que você aprovou.
3. **Arquivos de risco:** a branch contém `_prod_src.b64`, `_sftp_test.js` e outros artefatos em `vps-tools/` — potencial exposição de segredos operacionais (script de SFTP, base64 de fonte de produção). O gate P0 de conflitos e segredos precisa rodar antes de qualquer consideração de merge.

## 4. Recomendações

| # | Recomendação | Prioridade |
|---|---|---|
| 1 | **Não mesclar** `legal-tech-premium-design-72646` no estado atual | Obrigatória |
| 2 | Confirmar com você se houve realmente solicitação de desativar o 2FA — se não, o 2FA deve ser restaurado antes de qualquer uso dessa branch | Obrigatória |
| 3 | Se quiser aproveitar o design do GPT: rebase/merge de main → branch, restaurar `auth.py` inteiro da main (cherry-pick), e auditar diff de `pii_crypto`, sessões e rotas de casos | Condicional |
| 4 | Rodar o gate P0 (segredos) sobre a branch antes de qualquer ação | Obrigatória |
| 5 | Preferir evolução incremental do design já homologado (DT) em vez de substituição em bloco | Recomendada |

## 5. Observação final

A branch parece ser um "big-bang" de redesign gerado por IA sobre uma snapshot antiga, sem passar pelo protocolo de homologação (diagnóstico → correção → teste → regressão → homologação). O padrão que estabelecemos no EJC exige que qualquer redesign venha em PR pequeno, testado e com regressão comprovada. A única parte reaproveitável com segurança é a camada visual (CSS/Tailwind/components React), desde que isolada do backend — e `auth.py` **jamais** deveria entrar nessa categoria de "ajuste visual".
