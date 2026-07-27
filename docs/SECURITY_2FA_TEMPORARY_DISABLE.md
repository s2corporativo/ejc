# Política de 2FA — estado atual e como alternar

> **DECISÃO OPERACIONAL VIGENTE: o 2FA está DESLIGADO.** O escritório optou por
> não exigir autenticador; o login usa apenas senha. A desativação é declarada
> explicitamente em `docker-compose.yml`
> (`TWO_FACTOR_AUTH_ENABLED: "${TWO_FACTOR_AUTH_ENABLED:-false}"`), e não
> resulta de esquecimento de configuração.
>
> **O mecanismo é FAIL-CLOSED.** No código, o 2FA fica LIGADO por padrão: só é
> desativado quando `TWO_FACTOR_AUTH_ENABLED` recebe um valor **explicitamente
> falso**. Omitir a variável **não desativa** nada. Isto inverte a política
> anterior (auditoria de 26/07/2026), em que a ausência da variável desligava o
> 2FA silenciosamente — o risco ali não era a decisão de não usar 2FA, e sim
> não haver registro de que essa decisão havia sido tomada.
>
> Trocar de estado é uma mudança de variável: nada no banco muda, nenhum
> usuário precisa recadastrar o autenticador.

## Estado operacional

| `TWO_FACTOR_AUTH_ENABLED` | Efeito |
|---|---|
| variável ausente | **2FA ativo** |
| `true`, `1`, `yes`, `on`, `sim` | **2FA ativo** |
| qualquer valor não reconhecido | **2FA ativo** (falha fecha) |
| `false`, `0`, `no`, `off`, `nao`, `não` | **2FA desativado** ← configuração atual |

Enquanto desativado, a política alcança:

- login de contas que já possuíam TOTP ativo;
- exigência de configuração por papel (`REQUIRE_2FA_ROLES` é esvaziado em memória);
- renovação de sessão;
- tokens antigos com o claim `two_factor_setup_required`;
- troca obrigatória de senha seguida de configuração do autenticador.

O boot registra `WARNING` em `ejc.security` sempre que sobe desativado. A
ausência desse aviso no log é a confirmação de que o 2FA está exigido.

## Desativar o 2FA (estado atual)

Já é o estado configurado — este procedimento serve para reproduzir o ambiente
ou reverter uma ativação.

1. Definir **`TWO_FACTOR_AUTH_ENABLED=false`** no ambiente da aplicação — não
   basta remover a variável, e nenhum outro valor serve.
2. Reiniciar o backend.
3. Confirmar no log o `WARNING` de 2FA desativado (é o sinal de que a política
   foi aplicada de propósito, e não por configuração faltante).

## Ativar o 2FA

Quando o escritório decidir exigir o autenticador:

1. Definir `TWO_FACTOR_AUTH_ENABLED=true` no `.env` — ou remover a linha
   correspondente do `docker-compose.yml`, já que o padrão do código é ligado.
2. Reiniciar o backend para eliminar o cache de configurações e registrar a nova política.
3. Confirmar que o `WARNING` de desativação **não** aparece mais no boot.
4. Conferir os papéis em `REQUIRE_2FA_ROLES` (default: gestão + advogados).
5. Homologar login com e sem TOTP, refresh, troca de senha e logout.
6. Avisar a equipe **antes**: quem já tem TOTP cadastrado volta a ter o segundo
   fator exigido no próximo login, e os papéis listados passam a ser levados ao
   fluxo de configuração obrigatória.

Nenhuma migration ou recadastro do autenticador é necessário em nenhuma direção.

## Preservação dos dados

A desativação é somente de execução — nada é apagado:

- `users.totp_enabled` persistido no banco;
- `users.totp_secret` cifrado;
- eventos anteriores da trilha de auditoria.

Ao carregar um usuário, o valor de `totp_enabled` é suprimido apenas no objeto da
sessão SQLAlchemy. O estado armazenado continua disponível para reativação.
Enquanto o 2FA está desligado, os endpoints `/auth/totp/*` respondem 409 para
que ninguém sobrescreva um segredo TOTP existente.

## Proteções que permanecem ativas

Com o 2FA desligado continuam vigentes:

- senha forte e troca obrigatória de senha temporária;
- rate limit e bloqueio contra força bruta;
- refresh token rotativo;
- detecção de replay e revogação de sessões;
- cookie `httpOnly` para refresh;
- auditoria de login, dispositivo e falhas;
- segregação de papéis e carteiras.

## Risco aceito

Sem 2FA, a senha é o único fator: uma credencial vazada, reutilizada ou obtida
por phishing dá acesso direto a processos, documentos e dados de clientes. As
proteções acima reduzem, mas não substituem, o segundo fator.

Esta é uma decisão consciente do escritório, registrada aqui e no
`docker-compose.yml`. Convém reavaliá-la antes do go-live definitivo e sempre
que a carteira de clientes ou o volume de dados sensíveis crescer — o mecanismo
está pronto e é ligado com uma variável.

## Referências no código

- `backend/app/core/two_factor_policy.py` — decisão da política e supressão em runtime.
- `backend/app/core/auth_middleware.py` — bloqueio de `/auth/totp/*` na janela.
- `backend/tests/test_two_factor_policy.py` — regressão do comportamento fail-closed.
- `.env.example` — a flag e seu significado.
