# Desativação temporária do 2FA

## Estado

O 2FA está temporariamente desativado por `TWO_FACTOR_AUTH_ENABLED=false`.
A desativação alcança login, renovação de sessão e o gate do middleware.

## Preservação de dados

Nenhum segredo TOTP é apagado e nenhuma migration é necessária. Contas que
já possuíam autenticador configurado poderão voltar a utilizá-lo quando o
kill switch for reativado.

### Ressalva: auto-desativação durante a janela

Enquanto o kill switch está desligado, a guarda que impede um usuário de
papel obrigado de remover o próprio 2FA (`POST /api/auth/totp/desativar`)
também fica inativa. Um usuário que ainda tenha um código TOTP válido pode,
portanto, desativar o próprio autenticador nesse período — é ação do próprio
usuário e apaga apenas o segredo dele. Na reativação, esse usuário precisará
reinscrever o autenticador; a massa de segredos das demais contas permanece
intacta.

## Reativação

1. Definir `TWO_FACTOR_AUTH_ENABLED=true` no ambiente de produção.
2. Revisar `REQUIRE_2FA_ROLES`.
3. Reiniciar o backend.
4. Executar os testes de autenticação e homologar login/refresh/logout.

## Risco aceito

Enquanto desativado, a proteção depende de senha forte, rate limit, rotação
de refresh token, detecção de replay e trilha de auditoria. A decisão deve
ser reavaliada antes do go-live definitivo.
