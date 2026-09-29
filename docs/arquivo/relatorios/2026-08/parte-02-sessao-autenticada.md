# Auditoria Técnica do EJC — Parte 2: Sessão autenticada como Advogado
**Usuário de teste:** soares@depaulateixeira.adv.br (perfil `advogado`, nome "Clovis Soares")
**Método:** chamadas diretas e autenticadas à API REST (`/api/v1/...`) reproduzindo, endpoint a endpoint, o que a tela de cada módulo consulta. Não criei, editei nem excluí nenhum registro real do escritório — apenas leitura (GET), exatamente como a navegação normal de um advogado faria ao abrir cada módulo.
**Login:** bem-sucedido, `role: advogado`, token JWT válido, endpoints protegidos respondendo corretamente conforme perfil.

---

## 1. ACHADO CRÍTICO — Dashboard mostra dados que os módulos reais não mostram

Ao chamar `GET /dashboard/` autenticado como este advogado, a resposta (reproduzida de forma idêntica em duas chamadas separadas) foi:

```json
{"casos":{"por_status":{"triagem":3},"total":3,"ativos":3},
 "prazos":{"vencidos":0,"criticos_3d":1,"proximos_7d":1},
 "clientes_ativos":6, ...}
```

Ou seja: o painel inicial informa **3 casos ativos, 6 clientes ativos, 1 prazo crítico (vence em até 3 dias) e 1 prazo em até 7 dias**.

Ao chamar os endpoints que alimentam as telas reais desses módulos, para o **mesmo usuário, na mesma sessão**:

| Endpoint | O que deveria mostrar | O que retornou |
|---|---|---|
| `GET /cases/` | 3 casos | `{"data":[],"total":0}` |
| `GET /cases/stats` | 3 total / 3 ativos | `{"total":0,"ativos":0,"encerrados":0,"arquivados":0}` |
| `GET /clients/` | 6 clientes | `{"data":[],"total":0}` |
| `GET /deadlines/` | 2 prazos (1 crítico) | `{"data":[],"total":0}` |

**Isso é um erro funcional grave, não uma hipótese.** Testei com e sem parâmetros (`?responsavel_id=me`, `?escopo=todos`), em chamadas separadas, e o resultado foi consistentemente zero em todos os módulos de listagem, enquanto o Dashboard consistentemente reporta 3/6/2.

**Impacto prático para um advogado:** ele abre o sistema, vê no painel "você tem 1 prazo crítico vencendo em até 3 dias" — e ao clicar em Prazos (ou Casos, ou Clientes) para ver do que se trata e agir, encontra uma tela vazia. No pior cenário, isso significa **risco real de perda de prazo**, porque a única forma de saber que existe é o número solto no card do Dashboard, sem conseguir abrir o item para tratá-lo. Isto deveria ser tratado como bug de prioridade máxima antes de qualquer outra correção listada na Parte 1 deste relatório.

Não tenho acesso ao banco de dados para apontar a causa raiz exata, mas o padrão (endpoint agregado certo, endpoints de listagem errados) é tipicamente causado por: filtro de "responsável"/"tenant" divergente entre a query do dashboard e a query da listagem, diferença de tratamento de soft-delete (`deleted_at`) entre as duas consultas, ou cache do dashboard desatualizado/dessincronizado do dado real. Recomendo que o time técnico comece por comparar as duas queries SQL/ORM por trás de `/dashboard/` e de `/cases/`.

---

## 2. ACHADO CRÍTICO — Erro 500 reproduzível em Prazos

```
GET /api/v1/deadlines/?page_size=100&status=all
→ HTTP 500 — {"detail":"Erro interno. A equipe foi notificada."}
```

Reproduzido de forma consistente em duas chamadas. Os parâmetros usados (`page_size` maior e um filtro de status agregando "todos") são exatamente o tipo de ação que um advogado tomaria ao tentar ver *todos* os prazos de uma vez, ou que a própria tela dispararia ao "carregar mais" ou aplicar um filtro "Todos os status". Recomendo verificar o tratamento desse parâmetro `status=all` no backend — provavelmente o código espera um enum específico (ex.: `pendente`, `vencido`, `cumprido`) e quebra ao receber `all` sem tratamento explícito.

---

## 3. Achados de média severidade

**3.1 — Perfil do advogado testado está sem número de OAB cadastrado.**
`GET /users/me` retornou `"oab_number": null` e `"djen_oab_numero": null` para este usuário. Como o EJC tem módulos de captura automática de Intimações e monitoramento de Diário Oficial (que tipicamente dependem do número de OAB para filtrar publicações do próprio advogado), um cadastro de usuário sem OAB preenchida é um indício concreto de que a funcionalidade mais sensível do sistema — não deixar passar uma intimação — pode estar inoperante para este usuário especificamente. Recomendo tornar o campo OAB obrigatório no cadastro/onboarding de qualquer perfil `advogado`, com bloqueio ou alerta visível enquanto não preenchido.

**3.2 — Gestão de sessões não identifica a sessão atual.**
`GET /users/me/sessions` retornou 4 sessões ativas, todas com `"current": false`. Se a tela de "Sessões ativas" do Configurações usa esse mesmo campo para destacar "este dispositivo", o advogado não conseguiria saber qual sessão é a que está usando agora ao decidir encerrar as outras. Ressalva: posso ter obtido esse resultado porque autentiquei via token direto, sem replicar exatamente o cookie de sessão que o navegador real enviaria — recomendo que o time confirme isso numa sessão de navegador real antes de tratar como bug confirmado.

**3.3 — Mensagens de erro de permissão não padronizadas.**
Três endpoints administrativos testados devolveram três formatos diferentes de `403`:
- `/system-modules/mapa` → `"Acesso negado. Perfis permitidos: superadmin, admin, socio"`
- `/diagnostico/central` → `"Acesso negado. Perfis permitidos: socio"`
- `/ia-governanca/dashboard` → `"Acesso restrito a governanca da IA"` (sem listar perfis)

Não é um bug de segurança (o bloqueio em si funcionou corretamente nos três casos), mas é uma inconsistência de comunicação: padronizar o formato ajuda o próprio usuário a entender por que foi bloqueado e o que precisaria mudar (ex.: virar sócio) sem precisar perguntar ao suporte.

---

## 4. Confirmações positivas com dado real (reforçam a Parte 1)

- **Controle de acesso por perfil funcionando corretamente**: como `advogado`, recebi `403` de forma consistente em todos os 3 endpoints administrativos testados (Mapa de Módulos, Central de Diagnóstico, Governança da IA) — a segregação sócio/admin vs. advogado está implementada e funcionando.
- **Tratamento de recurso inexistente correto**: `GET /cases/{uuid-inexistente}` retorna `404` com mensagem clara (`"Caso não encontrado"`), sem vazar detalhe técnico.
- **Conteúdo de ajuda por módulo é real e estruturado**, não apenas texto estático da interface: `GET /module-help/` devolve markdown completo por módulo (o que faz, quando usar, passo a passo) — confirma com dado de API o que já havia sido identificado na Parte 1 a partir do bundle público.
- **Catálogo de tipos de peça jurídica é extenso e tecnicamente correto**: `GET /pecas/meta` lista tipos como petição inicial, contestação, réplica, recurso ordinário, apelação, contrarrazões, embargos de declaração, agravo, cumprimento de sentença — nomenclatura processual correta e agrupada por fase (inicial/pós-decisão/recursal).

---

## 5. Observação de segurança operacional (fora do escopo técnico do EJC, mas relevante)

A senha de aplicação fornecida para este teste (`soares@depaulateixeira.adv.br`) é **idêntica** à senha de root da VPS fornecida anteriormente nesta mesma conversa. Reutilizar a mesma senha entre acesso de infraestrutura (root/SSH do servidor) e uma conta de aplicação nomeada de um usuário é prática de risco: o vazamento de uma credencial compromete as duas superfícies simultaneamente. Recomendo, independente de qualquer achado deste relatório: (a) trocar a senha de root da VPS por uma exclusiva, (b) migrar o acesso SSH de senha para autenticação por chave (mais seguro e evita o problema por completo), e (c) usar um gerenciador de senhas com geração única por sistema.

---

## 6. O que fica pendente

Não testei fluxos de escrita (criar caso, criar cliente, protocolar peça, registrar prazo) porque isso criaria registros reais no banco de produção do escritório — decisão deliberada para não poluir dados reais sem autorização explícita. Se quiserem que eu valide também os fluxos de criação/edição (essenciais para saber se o problema do item 1 é só de leitura ou se cadastrar um caso novo também falha em aparecer na listagem), posso fazer isso mediante autorização explícita para criar e depois excluir um registro de teste identificado claramente como teste (ex.: cliente "TESTE AUDITORIA — EXCLUIR").
