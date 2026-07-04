---
name: edicao-cirurgica
description: >
  Edição cirúrgica: retorna APENAS blocos modificados, nunca o artefato inteiro. Use SEMPRE que o usuário pedir para modificar, corrigir, ajustar, refatorar ou remover trecho de código, JSON, SQL, HTML, CSS, Markdown, workflow n8n ou qualquer artefato existente. Acionar também em edição iterativa multi-rodada: "ajusta o bloco de pedidos", "troca a seção 3", "muda o nó X", "corrige o CSS", "mexe na função", "edita o bloco de", "atualiza só essa parte", "refatora isso". Cobre todas as linguagens e formatos. NAO usar para criação do zero (skill geradora tem prioridade) nem quando mais de 70% do artefato muda.
---

# Skill: Edição Cirúrgica

## Princípio Central

Quando propor alterações em artefato existente, retorne **apenas o delta**  -  o bloco que mudou. Jamais reescreva o artefato inteiro. Isso preserva contexto, reduz consumo de tokens e evita sobrescrever acidentalmente partes não alteradas.

---

## Escopo de Aplicação

Esta skill governa **dois modos de operação**, dependendo de onde o artefato vive:

### Modo 1  -  Edição direta em arquivo (container)

Quando o arquivo está disponível no filesystem (`/home/claude/`, `/mnt/user-data/`), usar a ferramenta nativa `str_replace`:

```
str_replace(
  path: "caminho/do/arquivo",
  old_str: "trecho exato a substituir",
  new_str: "trecho novo"
)
```

Neste modo, **não** formatar a entrega como bloco visual  -  a ferramenta já é cirúrgica por natureza. Apenas explicar brevemente o que mudou e por quê.

### Modo 2  -  Sugestão conversacional (código externo)

Quando o artefato **não está no container** (repositório local do usuário, workflow n8n, Supabase, Google Apps Script, arquivo que o usuário vai copiar manualmente), usar o formato visual padronizado descrito abaixo.

---

## Formato Visual Padrão (Modo 2)

```
📄 Artefato: `caminho/do/arquivo.ext` ou `nome do workflow / nó`
🔧 Bloco: `nomeDaFuncao` | `seção X` | `nó "Nome do Nó"` | `cláusula WHERE`
✏️ Ação: substituir | adicionar após [referência] | remover

```[linguagem]
// ... código/conteúdo existente acima ...

[BLOCO ALTERADO AQUI]

// ... código/conteúdo existente abaixo ...
```
```

### Regras do formato

- **Sempre** indicar artefato, bloco e ação  -  sem esses três, o usuário não sabe onde encaixar
- **Marcadores de continuidade** representam o conteúdo inalterado:
  - JS/TS: `// ... código existente ...`
  - Python: `# ... restante da classe ...`
  - SQL: `-- ... demais colunas inalteradas ...`
  - HTML/CSS: `<!-- ... seções inalteradas ... -->`
  - JSON: `"...": "/* demais campos inalterados */"`
  - Markdown: `<!-- ... restante do documento ... -->`
- **Múltiplas alterações no mesmo artefato**: um bloco por ponto de edição, na ordem em que aparecem no artefato original
- **Múltiplos artefatos**: separar com cabeçalho `📄 Artefato:`  -  nunca misturar

---

## Edição Iterativa de Documentos

Em fluxos de construção por blocos (petições, pareceres, contratos, skills, workflows), o padrão cirúrgico se aplica com força especial:

### Contexto típico

O usuário e o Claude estão construindo um artefato em múltiplas rodadas. A cada rodada, o usuário pede ajustes em blocos específicos do que já foi gerado. O artefato pode ser:

- Peça jurídica em construção (fundamentação já pronta, agora ajustar os pedidos)
- Skill sendo refinada (trigger já definido, agora expandir as regras de redação)
- Workflow n8n sendo iterado (nó de trigger pronto, agora corrigir o Code Tool)
- HTML/CSS de documento timbrado (cabeçalho pronto, agora ajustar o footer)
- Script Python ou Apps Script em desenvolvimento

### Regras para edição iterativa

1. **Nunca regenerar o artefato completo** quando o pedido se refere a um bloco específico
2. **Referenciar o bloco pelo identificador natural**: nome da seção, nome da função, número do slide, nome do nó n8n, seletor CSS, número da cláusula contratual
3. **Preservar o que já foi aprovado**: se o usuário aprovou a fundamentação e agora pede ajuste nos pedidos, a fundamentação não aparece na resposta
4. **Entregar o bloco editado completo**: não entregar "meia função"  -  o bloco inteiro que mudou, com marcadores de continuidade antes e depois
5. **Quando houver dúvida sobre o escopo**: perguntar "você quer que eu ajuste só [bloco X] ou reescreva a seção inteira?"

---

## Regras Específicas por Tipo de Artefato

### Código (JS, TS, Python, Apps Script, SQL)

- Retornar a função/método/bloco inteiro que mudou, não apenas a linha
- Se a alteração impacta imports, mostrar o import novo separadamente como bloco adicional
- Nunca reescrever boilerplate (setup Express, setup Next.js, etc.) que não mudou

### Workflows n8n (JSON)

- Identificar o nó pelo campo `"name"`  -  retornar apenas o objeto do nó alterado
- Se a alteração é no `jsCode` de um Code Tool, retornar apenas o nó com o `jsCode` atualizado
- Se a alteração é em `connections`, retornar apenas o bloco de connections afetado
- **Regra crítica**: nunca alterar o `webhookId` do MCP Server Trigger (`0199517e-f508-4cc9-8dd4-9532ffa42e6c`) em edições parciais  -  isso quebra a URL de conexão Claude ↔ n8n
- Para alterações que afetam nó + connection, entregar dois blocos separados e identificados

### HTML/CSS (documentos timbrados, landing pages, artefatos visuais)

- Identificar o bloco pelo seletor CSS ou pelo elemento semântico (`<header>`, `<section class="pedidos">`, `<footer>`)
- Se a alteração é só CSS, retornar apenas o bloco `<style>` ou o seletor específico
- Nunca reescrever o HTML inteiro quando só o CSS mudou, e vice-versa

### Skills (SKILL.md)

- Identificar a seção pelo heading Markdown (`## Regras de Redação`, `## Trigger`, etc.)
- Se o trigger (description no frontmatter) mudou, retornar apenas o bloco `---` do frontmatter
- Se uma seção interna mudou, retornar apenas aquela seção com heading + conteúdo

### Documentos jurídicos em construção

- Identificar o bloco pelo nome estratégico: "endereçamento", "qualificação", "fundamentação  -  tese X", "pedidos", "fechamento"
- Respeitar a construção em blocos do padrão do escritório: nunca fundir blocos que o usuário separou
- Se o ajuste é em um parágrafo específico dentro de uma seção, citar o parágrafo anterior como âncora de referência

---

## O que NÃO fazer

| Proibido | Correto |
|---|---|
| Colar o artefato inteiro com a linha alterada no meio | Colar só o bloco alterado |
| Reescrever imports/headers/boilerplate que não mudaram | Usar marcador de continuidade |
| Misturar blocos de artefatos diferentes sem separação | Separar por `📄 Artefato:` |
| Omitir onde a alteração se encaixa | Sempre informar artefato + bloco + ação |
| Regenerar seções aprovadas de um documento iterativo | Entregar só o bloco que o pedido menciona |
| Tocar no `webhookId` do MCP Trigger em edições n8n | Preservar IDs críticos como regra inviolável |
| Entregar "meia função" (só as linhas que mudaram sem contexto) | Entregar o bloco/função inteiro que mudou |

---

## Quando é aceitável entregar o artefato inteiro

Apenas se:

- O usuário **pedir explicitamente** ("me manda o arquivo completo", "reescreve tudo", "consolida tudo")
- O artefato tiver menos de ~30 linhas e a alteração impactar mais de 70% dele
- For a **primeira versão** do artefato (criação, não edição)  -  neste caso a skill geradora específica tem prioridade

---

## Exemplo Prático  -  Edição Iterativa de Petição

**Contexto:** Fundamentação já entregue e aprovada. Usuário pede: "Ajusta os pedidos, preciso incluir pedido de tutela de urgência."

**Errado:**
```
[Reescreve a petição inteira  -  4 páginas  -  para adicionar um pedido]
```

**Correto:**
```
📄 Artefato: Petição  -  Ação Anulatória de Débito Fiscal
🔧 Bloco: Seção de Pedidos (após "DOS PEDIDOS")
✏️ Ação: substituir

Diante do exposto, requer a Vossa Excelência:

a) a concessão de tutela de urgência, inaudita altera parte, para
suspender a exigibilidade do crédito tributário objeto do Auto de
Infração nº XX/2025, nos termos do artigo 300 do CPC c/c artigo
151, V, do CTN, ante o fundado risco de inscrição em dívida ativa
e consequente restrição cadastral;

b) a citação da parte ré para, querendo, contestar a presente no
prazo legal;

c) no mérito, a procedência dos pedidos para declarar a nulidade
do Auto de Infração nº XX/2025, com o consequente cancelamento
do crédito tributário no valor de R$ 150.000,00 (cento e cinquenta
mil reais);

d) a condenação da parte ré ao pagamento de honorários
advocatícios e custas processuais.

<!-- ... fechamento e assinatura inalterados ... -->
```

---

## Exemplo Prático  -  Edição de Nó n8n

**Contexto:** Workflow MCP com 10 Code Tools. Usuário pede: "Corrige o Code Tool Create  -  o parse do JSON está falhando quando recebe workflow_json aninhado."

**Correto:**
```
📄 Artefato: Workflow MCP Server (ID: WP146hNfuetOQ1kW)
🔧 Nó: "Code Tool Create" (id: da4d888e-...)
✏️ Ação: substituir campo `jsCode`
```

```javascript
const API_KEY = '...';
const BASE = 'https://n8n-production-a84a.up.railway.app';
let workflowData;
try {
  const parsed = JSON.parse(query);
  // FIX: suporta wrapper workflow_json e também objeto direto
  workflowData = parsed.workflow_json || parsed;
  // Validação mínima
  if (!workflowData.name && !workflowData.nodes) {
    return JSON.stringify({ error: true, message: 'Payload deve conter name e/ou nodes' });
  }
} catch (e) {
  return JSON.stringify({ error: true, message: 'JSON invalido: ' + e.message });
}
// ... restante do fluxo de criação inalterado ...
```
