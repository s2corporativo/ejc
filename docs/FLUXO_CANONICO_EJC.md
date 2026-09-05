# FLUXO CANÔNICO DO EJC

> Define o caminho único de cada operação no sistema. Existe para impedir caminhos
> duplicados criados por agentes distintos em momentos distintos.
>
> As seções de fluxo exigem preenchimento humano: descrevem decisão de produto,
> não estrutura extraível do código. Use `docs/MATRIZ_DE_ROTAS.md` (gerada) como insumo.

---

## 1. Princípio

Para cada operação de negócio existe **um** caminho canônico. Caminho alternativo só
existe se estiver registrado aqui, com justificativa. Caminho não registrado é
duplicação e deve ser removido.

Antes de implementar qualquer entrada nova, o agente verifica se a operação já possui
caminho canônico. Se possuir, estende o existente — não cria outro.

---

## 2. Operações canônicas

| # | Operação | Entrada única | Rota backend | Componente frontend | Pré-condição | Efeito | Caminho alternativo autorizado |
|---|---|---|---|---|---|---|---|
| 1 | Autenticar | | | | | | |
| 2 | Cadastrar cliente | | | | | | |
| 3 | Abrir caso | | | | | | |
| 4 | Vincular documento | | | | | | |
| 5 | Registrar prazo | | | | | | |
| 6 | Gerar peça | | | | | | |
| 7 | Revisar peça | | | | | | |
| 8 | Encerrar caso | | | | | | |

Ajustar a lista às operações reais do sistema.

---

## 3. Ciclo de vida do caso

Estados e transições permitidas. Transição não listada é defeito.

```
triagem → em análise → ativo → suspenso → ativo → encerrado → arquivado
```

| De | Para | Quem pode | Pré-condição | Registro obrigatório |
|---|---|---|---|---|
| | | | | |

---

## 4. Ciclo de vida da peça

```
rascunho → em revisão → corrigida → aprovada → versão final → exportada → protocolada
```

| De | Para | Quem pode | Pré-condição | Registro obrigatório |
|---|---|---|---|---|
| | | | | |

Regra fixa: peça gerada por IA não transita para `versão final` sem passagem por
`em revisão` com revisor humano identificado.

---

## 5. Perfis e permissões

Perfis conforme `ROLE_LEVEL` em `backend/app/core/security.py` — hierarquia numérica,
nível maior herda o alcance do menor. Alterar a lista aqui sem alterar o código (ou o
inverso) é divergência de contrato e defeito de revisão.

| Perfil | Nível | Pode criar | Pode editar | Pode aprovar | Pode excluir | Vê dados de outro escritório |
|---|---|---|---|---|---|---|
| `superadmin` | 9 | | | | | não |
| `admin` | 8 | | | | | não |
| `socio` | 7 | | | | | não |
| `advogado` | 6 | | | | | não |
| `advogado_auxiliar` | 5 | | | | | não |
| `financeiro` | 4 | | | | | não |
| `estagiario` | 3 | | | | | não |
| `secretaria` | 2 | | | | | não |
| `cliente_externo` | 1 | | | | | não |

Nenhum perfil enxerga dados de outro escritório. Exceção exigiria alteração deste
documento e revisão de segurança.

Ato jurídico exige `advogado` ou superior — gate único em `requer_advogado()`.
`cliente_externo` acessa apenas o portal (`/portal`), nunca a área staff.

---

## 6. Pontos de decisão humana obrigatória

Operações que não podem ser automatizadas nem executadas por agente:

- Aprovação de peça para protocolo
- Merge e release
- Fechamento de PR
- Alteração de regra jurídica sem fonte oficial
- Exclusão de dado de cliente
- Concessão de acesso a dado sigiloso

---

## 7. Anti-padrões proibidos

| Anti-padrão | Por quê | Verificação |
|---|---|---|
| Duas telas criando a mesma entidade | Divergência de validação | `MATRIZ_DE_ROTAS.md` seção 3 |
| Rota nova replicando rota existente | Contrato duplicado | `MATRIZ_DE_ROTAS.md` seção 1 |
| Validação apenas no frontend | Contornável | Revisão de PR, camada B |
| Estado de caso alterado sem registro | Perda de auditoria | Revisão de PR, camada E |
| Consulta sem filtro de escritório | Vazamento entre tenants (P0) | Revisão de PR, camada B |
