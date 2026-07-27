# Desativação temporária do 2FA (procedimento de emergência)

> **Política vigente: FAIL-CLOSED.** O 2FA fica **LIGADO** por padrão. Ele só é
> desativado quando `TWO_FACTOR_AUTH_ENABLED` recebe um valor **explicitamente
> falso**. Omitir a variável **não desativa** nada — um deploy que esqueça a flag
> roda com 2FA exigido, que é o comportamento desejado.
>
> Isto inverte a política anterior (auditoria de 26/07/2026), em que a ausência
> da variável desligava o 2FA silenciosamente.

## Estado operacional

| `TWO_FACTOR_AUTH_ENABLED` | Efeito |
|---|---|
| variável ausente | **2FA ativo** |
| `true`, `1`, `yes`, `on`, `sim` | **2FA ativo** |
| qualquer valor não reconhecido | **2FA ativo** (falha fecha) |
| `false`, `0`, `no`, `off`, `nao`, `não` | **2FA desativado** (janela de emergência) |

Enquanto desativado, a política alcança:

- login de contas que já possuíam TOTP ativo;
- exigência de configuração por papel (`REQUIRE_2FA_ROLES` é esvaziado em memória);
- renovação de sessão;
- tokens antigos com o claim `two_factor_setup_required`;
- troca obrigatória de senha seguida de configuração do autenticador.

O boot registra `WARNING` em `ejc.security` sempre que sobe desativado. A
ausência desse aviso no log é a confirmação de que o 2FA está exigido.

## Desativação de emergência

1. Registrar a justificativa e o responsável (a decisão é de gestão, não do plantão).
2. Definir **`TWO_FACTOR_AUTH_ENABLED=false`** no ambiente da aplicação — não
   basta remover a variável, e nenhum outro valor serve.
3. Reiniciar o backend.
4. Confirmar no log o `WARNING` de 2FA desativado.
5. Abrir prazo de reativação: esta é uma janela temporária, não um estado.

## Reativação (retorno ao padrão)

1. **Remover** a variável `TWO_FACTOR_AUTH_ENABLED` do ambiente — ou defini-la
   como `true`. Ambos resultam em 2FA ativo.
2. Reiniciar o backend para eliminar o cache de configurações e registrar a nova política.
3. Confirmar que o `WARNING` de desativação **não** aparece mais no boot.
4. Confirmar os papéis em `REQUIRE_2FA_ROLES`.
5. Homologar login com e sem TOTP, refresh, troca de senha e logout.

Nenhuma migration ou recadastro do autenticador é necessário.

## Preservação dos dados

A desativação é somente de execução. O sistema não apaga:

- `users.totp_enabled` persistido no banco;
- `users.totp_secret` cifrado;
- eventos anteriores da trilha de auditoria.

Ao carregar um usuário, o valor de `totp_enabled` é suprimido apenas no objeto da
sessão SQLAlchemy. O estado armazenado continua disponível para reativação.
Enquanto a janela estiver aberta, os endpoints `/auth/totp/*` respondem 409 para
que ninguém sobrescreva um segredo TOTP existente.

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

## Referências no código

- `backend/app/core/two_factor_policy.py` — decisão da política e supressão em runtime.
- `backend/app/core/auth_middleware.py` — bloqueio de `/auth/totp/*` na janela.
- `backend/tests/test_two_factor_policy.py` — regressão do comportamento fail-closed.
- `.env.example` — a flag e seu significado.
