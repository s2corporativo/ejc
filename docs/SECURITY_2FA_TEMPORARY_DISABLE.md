# Desativação temporária do 2FA

## Estado operacional

O EJC considera o 2FA desativado enquanto a variável
`TWO_FACTOR_AUTH_ENABLED` não estiver definida como `true`.

A política alcança:

- login de contas que já possuíam TOTP ativo;
- exigência de configuração por papel;
- renovação de sessão;
- tokens antigos com o claim `two_factor_setup_required`;
- troca obrigatória de senha seguida de configuração do autenticador.

## Preservação dos dados

A desativação é somente de execução. O sistema não apaga:

- `users.totp_enabled` persistido no banco;
- `users.totp_secret` cifrado;
- eventos anteriores da trilha de auditoria.

Ao carregar um usuário, o valor de `totp_enabled` é suprimido apenas no objeto da
sessão SQLAlchemy. O estado armazenado continua disponível para reativação.

## Reativação

1. Definir `TWO_FACTOR_AUTH_ENABLED=true` no ambiente da aplicação.
2. Reiniciar o backend para eliminar o cache de configurações e registrar a nova política.
3. Confirmar os papéis em `REQUIRE_2FA_ROLES`.
4. Homologar login com e sem TOTP, refresh, troca de senha e logout.

Nenhuma migration ou recadastro do autenticador é necessário.

## Proteções que permanecem ativas

Durante a suspensão do 2FA continuam vigentes:

- senha forte e troca obrigatória de senha temporária;
- rate limit e bloqueio contra força bruta;
- refresh token rotativo;
- detecção de replay e revogação de sessões;
- cookie `httpOnly` para refresh;
- auditoria de login, dispositivo e falhas;
- segregação de papéis e carteiras.

## Risco aceito

A suspensão reduz a resistência contra comprometimento de senha. Deve permanecer
temporária e ser reavaliada antes da certificação final e do go-live definitivo.
