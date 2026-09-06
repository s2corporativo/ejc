# Revisão crítica — `backend/app/routers/auth.py` na branch de design do GPT

**Branch analisada:** `legal-tech-premium-design-72646` (commit `c691274f`,
autor `qwen.ai[bot]`, 22/07/2026 — mais de um mês atrás).
**Base de comparação:** `a1c6d2d1` (merge-base com `main`), versão anterior às
correções de produção atuais; a homologação M03/M04 validou a versão corrente
de `main`.

## 1. Natureza e alcance das alterações

O commit remove **525 linhas** de `auth.py` (de 865 para 340) e **não adiciona
nenhuma linha de código funcional** — todas as inserções são comentários. A
removal concentrada é o **2FA/TOTP completo**:

| Componente removido | Função de segurança |
|---|---|
| `pyotp` e `totp_code` no `LoginRequest` | Verificação do segundo fator no login |
| Bloco 3 do login (`if user.totp_enabled`) | Bloqueio de login sem código TOTP quando 2FA ativo |
| `/totp/setup` | Ativação do autenticador (QR code) |
| `/totp/verificar` (com rate limit 10/min) | Confirmação do TOTP |
| `/totp/desativar` (com rate limit 10/min) | Desativação com confirmação |
| `TOTPVerificarRequest` / `TOTPDesativarRequest` | Schemas de validação |

## 2. O que foi preservado (verificado)

A anti-força-bruta (bloco 1 do login), o alerta de novo dispositivo
(`verificar_novo_dispositivo`, linha 166+), o fluxo de troca/recuperação de
senha e todos os demais endpoints (`/login`, `/refresh`, `/logout`,
`/alterar-senha`, `/recuperar-senha`, `/redefinir-senha`) permanecem intactos.
A sintaxe do arquivo resultante é válida (py_compile OK). Não há nenhuma
alteração não relacionada a TOTP: **não há backdoor, exposição de dados,
remoção de auditoria ou weaken de força-bruta**.

## 3. Pontos de risco identificados

**R1 — Quebra funcional com o frontend atual (consequência, não backdoor).**
`frontend/src/components/AccountSecurity.tsx` (linhas 89, 109, 130) e
`pages/Configurar2FA.tsx` continuam chamando `/auth/totp/setup`,
`/auth/totp/verificar` e `/auth/totp/desativar`. Com os endpoints removidos,
as telas de segurança da conta retornariam 404. O frontend teria de ser
ajustado no mesmo merge (remover/adaptar AccountSecurity e Configurar2FA).

**R2 — Decisão de segurança deve ser formal do Dr. Clovis.** O GPT registrou
"2FA/TOTP desativado conforme solicitação" — mas **não há registro desta
solicitação no processo desta campanha**. A desativação do 2FA enfraquece o
controle de acesso do escritório (papéis sensíveis como admin/socio/financeiro
passam a depender só de senha + rate limit). Se a intenção for manter o 2FA,
esse trecho deve ser **integralmente revertido**.

**R3 — Endpoints comentados são código morto perigoso.** O padrão "comentar em
vez de remover" (linhas 338+) cria código morto que não roda, não é testado e
pode ser "reativado" acidentalmente. Se a desativação for confirmada, a
remoção limpa (com migration de coluna se aplicável) é preferível; se não,
restaurar o código original.

**R4 — `pyotp` desaparece do arquivo mas o import pode falhar em runtime?**
Não — o `import pyotp` foi removido e a sintaxe valida; porém a coluna
`totp_secret`/`totp_enabled` segue no modelo `User` e na base (migrações
preservadas), o que é consistente (campos órfãos inofensivos).

## 4. Parecer

O diff é **tecnicamente limpo e focado** — não há indício de regressão de
segurança além da própria remoção do 2FA, que é uma decisão de política de
acesso, não um defeito de código. O risco real é: (a) telas de 2FA do
frontend quebradas se mergeado sem ajuste; (b) perda de segundo fator de
autenticação para papéis sensíveis, contrariando boas práticas de LGPD/controle
de acesso adotadas na homologação M03/M04 (19/19 PASS com 2FA habilitado).

**Recomendação:** manter o 2FA (reverter as alterações de `auth.py` no merge do
design) OU, se o Dr. Clovis confirmar a desativação do 2FA, proceder com o
ajuste coordenado do frontend (AccountSecurity/Configurar2FA) e remoção limpa
dos endpoints comentados. Nenhuma outra parte do design system toca o backend.
