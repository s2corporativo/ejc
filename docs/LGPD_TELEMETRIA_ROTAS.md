# LGPD — Telemetria de uso de rotas (`route_usage_metrics`)

Registro da atividade de tratamento criada nas Ondas 3–5 e das decisões tomadas
após a auditoria de segurança (achado **P2-3**).

## Finalidade

Medir se rotas candidatas à remoção (telas legadas e duplicatas depreciadas)
ainda são usadas, para decidir a retirada com dado real em vez de suposição.
Sem esta medição, a remoção seria feita às cegas.

## Dados tratados

| Campo | Conteúdo | Observação |
|---|---|---|
| `rota` | template do endpoint (`/api/tasks/{task_id}`) | nunca o path concreto |
| `metodo` | verbo HTTP | — |
| `papel` | papel RBAC (`advogado`, `admin`…) | **não** o usuário |
| `hora` | bucket horário UTC | granularidade de hora |
| `contagem` | nº de chamadas no bucket | agregado |

**Nunca coletados**: `user_id`, IP, querystring, corpo da requisição, número de
caso, nome ou qualquer identificador direto.

## Classificação honesta

Isto **não é anonimização**. Em papel com titular único (tipicamente
`superadmin`), a tupla `(papel, rota, hora)` é registro de comportamento de
pessoa identificável **por associação** — dado pessoal na acepção do
art. 5º, I da LGPD. A rotulagem anterior ("sem PII") foi corrigida no código
para "sem identificadores diretos", que é o que de fato se garante.

- **Base legal**: legítimo interesse (art. 7º, IX) — manutenção e evolução
  segura do sistema, com dados mínimos e sem decisão automatizada sobre pessoas.
- **Titulares**: usuários internos do escritório (staff).

## Mitigações aplicadas

1. **k-anonimato no recorte por papel** (`_K_ANONIMATO = 5`): papéis com menos
   de 5 eventos na janela são colapsados em `outros`, e a resposta marca
   `papeis_generalizados: true`.
   *Por que esta e não a redução de hora→dia*: a decisão da Onda 5 depende do
   **total por rota**, que o k-anonimato preserva intacto; o recorte por papel é
   apenas diagnóstico. Reduzir a granularidade temporal degradaria a leitura da
   janela (correlação com restarts e com o intervalo de flush) e **continuaria**
   permitindo singularizar o titular único em `(papel, dia)` — resolveria menos
   e custaria mais.
2. **Retenção máxima de 90 dias** (`RETENCAO_DIAS`), com expurgo automático
   diário (job `telemetria_rotas_expurgo`, 03:40). A janela de decisão declarada
   é de 30–60 dias, então 90 dias cobre o uso legítimo com folga.
3. **Acesso restrito**: leitura só por `require_admin` em
   `GET /api/architecture/uso-rotas`.

## Onde vive

- Serviço: `backend/app/services/route_usage.py`
- Modelo/tabela: `backend/app/models/route_usage_metric.py` → `route_usage_metrics`
- Migration: `backend/alembic/versions/122_route_usage_metrics.py`
- Coleta: `backend/app/core/auth_middleware.py` (`_registrar_uso_de_rota`)
- Leitura: `backend/app/routers/architecture.py` (`/architecture/uso-rotas`)

## Encerramento

Concluída a decisão da Onda 5 (remoção ou manutenção das rotas), este tratamento
perde a finalidade: remover o job, a coleta e **dropar a tabela** — o expurgo de
90 dias não substitui a eliminação ao fim da finalidade.
