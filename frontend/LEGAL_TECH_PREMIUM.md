# Legal Tech Premium — Design System EJC

## Visão Geral

Estilo **Legal Tech Premium** para o EJC (Escritório Jurídico Computadorizado): moderno e tecnológico, mas sóbrio o suficiente para um sistema jurídico profissional.

## Direção Visual

### 1. Fundo Branco com Profundidade Discreta

- **Fundo geral**: `#FFFFFF`
- **Áreas secundárias**: `#F7F9FC`
- **Cards**: branco
- **Bordas**: `#E5EAF0`
- **Sombras**: muito leves
- **Cantos arredondados**: 10–14 px

O sistema não fica "chapado". A profundidade vem de bordas, espaçamento e sombras suaves.

### 2. Identidade de Cores

| Aplicação                  | Cor                    | Hex       |
| -------------------------- | ---------------------- | --------- |
| Cor institucional          | Azul-marinho           | `#0B1F3A` |
| Cor tecnológica            | Azul elétrico          | `#2563EB` |
| IA e recursos inteligentes | Violeta                | `#7C3AED` |
| Sucesso                    | Verde-petróleo         | `#0F9D8A` |
| Atenção                    | Âmbar                  | `#D97706` |
| Erro ou prazo crítico      | Vermelho               | `#DC2626` |
| Texto principal            | Grafite                | `#172033` |
| Texto secundário           | Cinza médio            | `#667085` |

**Nota**: Azul e violeta aparecem em pequenos detalhes, ícones, estados ativos e indicadores da IA. Evitar degradês espalhados pelo sistema.

## Estrutura da Tela

### Cabeçalho Superior

Barra fixa de 64px contendo:
- Pesquisa global (com atalho Ctrl+K)
- Botão destacado "Novo atendimento"
- Acesso rápido ao Raio-X
- Botão do assistente de IA
- Notificações (com badge)
- Foto, nome e perfil do usuário

### Menu Lateral

Largura: 240px (recolhível para 84px)

**Organização sugerida**:
- Dashboard
- Triagem e Raio-X
- Clientes
- Casos
- Agenda e tarefas
- Documentos
- Conhecimento jurídico
- Financeiro
- Administração

**Item ativo**: fundo azul muito claro (`#EFF6FF`), ícone azul (`#2563EB`), barra lateral esquerda de 3px.

### Logomarca

Centralizada em dois lugares:
1. **Tela de login**: acima do formulário
2. **Topo do menu lateral**: perfeitamente centralizada

**Não colocar** no centro do Dashboard (ocupa espaço operacional).

## Dashboard

O Dashboard é uma **central de comando**, sem informações financeiras detalhadas.

### Primeira Faixa
- Saudação e data
- Campo de pesquisa
- "Novo atendimento"
- "Analisar documento"
- "Cadastrar manualmente"

### Segunda Faixa — Atenção Imediata
- Prazos críticos
- Intimações para validar
- Tarefas vencidas
- Peças aguardando revisão
- Clientes aguardando retorno

### Terceira Faixa
- Agenda do dia
- Casos sem próxima ação
- Documentos pendentes
- Atividades recentes

### Quarta Faixa
- Notícias jurídicas
- Atualizações legislativas
- Situação das integrações
- Alertas do sistema

## Cards Modernos

Cards funcionais, não apenas decorativos. Cada card apresenta:
- Ícone
- Título curto
- Quantidade (em destaque)
- Indicação de urgência (badge)
- Resumo da pendência
- Ação direta (link)

**Exemplo**:
```
7 prazos próximos
2 ainda não foram conferidos
Revisar prazos →
```

**Cores**: Card normal permanece branco; vermelho e âmbar aparecem apenas quando existe risco real.

## Aparência da IA

Identidade visual própria, integrada ao EJC:
- Ícone violeta discreto (`#7C3AED`)
- Botão "Analisar com IA"
- Painel lateral contextual
- Fontes utilizadas sempre visíveis
- Indicação de confiança (%)
- Separação entre fato, inferência e recomendação
- Ações: "Aprovar", "Corrigir", "Descartar"

**Evitar**: grande caixa de chatbot ocupando o Dashboard. A IA surge ao lado do documento/caso/peça sendo analisado.

## Tipografia e Componentes

- **Fonte**: Inter ou Manrope
- **Títulos**: peso 600
- **Texto comum**: 14–16 px
- **Ícones**: lineares (Lucide)
- **Botões**: altura mínima 40 px
- **Tabelas**: cabeçalho fixo
- **Filtros**: em chips
- **Menus de ações**: três pontos
- **Formulários**: divididos em etapas curtas
- **Loading**: skeleton (evitar telas vazias)

## O Que Evitar

- ❌ Excesso de azul escuro
- ❌ Fundo preto ou "modo gamer" como padrão
- ❌ Degradês em todos os cards
- ❌ Efeitos de vidro em tabelas e formulários
- ❌ Animações demoradas
- ❌ Cards com informações repetidas
- ❌ Muitos tipos de botão
- ❌ Ícones sem texto em funções importantes
- ❌ Telas com grandes áreas vazias
- ❌ IA visualmente separada do fluxo do caso

## Implementação Técnica

### Arquivos Criados

1. **`src/styles/legal-tech-premium.css`** — Design System completo
   - Variáveis CSS customizadas
   - Componentes (cards, botões, inputs, badges, tabelas)
   - Utilitários de layout e tipografia
   - Painel de IA especializado

2. **`src/components/DashboardLegalTechPremium.tsx`** — Componente de demonstração
   - Header superior fixo
   - Menu lateral com logo centralizada
   - Dashboard com 4 faixas de conteúdo
   - Cards de estatísticas e ações
   - Painel da IA integrado

3. **`tailwind.config.js`** — Extensão de cores
   - Adicionada paleta `legal` com todas as cores do design system

4. **`src/index.css`** — Integração
   - Import do Legal Tech Premium CSS
   - Variáveis de sobreposição opcionais

### Classes Principais

#### Layout
- `.lt-shell` — Container principal
- `.lt-header` — Cabeçalho superior fixo
- `.lt-sidebar` — Menu lateral
- `.lt-main` — Conteúdo principal

#### Cards
- `.lt-card` — Card padrão
- `.lt-stat-card` — Card de estatística/KPI
- `.lt-ai-panel` — Painel da IA

#### Botões
- `.lt-btn .lt-btn-primary` — Botão primário (azul elétrico)
- `.lt-btn .lt-btn-secondary` — Botão secundário (branco com borda)
- `.lt-btn .lt-btn-ghost` — Botão fantasma (transparente)

#### Badges
- `.lt-badge .lt-badge-blue` — Azul
- `.lt-badge .lt-badge-green` — Verde (sucesso)
- `.lt-badge .lt-badge-amber` — Âmbar (atenção)
- `.lt-badge .lt-badge-red` — Vermelho (crítico)
- `.lt-badge .lt-badge-violet` — Violeta (IA)

#### Utilitários
- `.lt-flex-center` — Flexbox centralizado
- `.lt-flex-between` — Flexbox com espaço entre
- `.lt-text-*` — Cores de texto
- `.lt-bg-*` — Cores de fundo
- `.lt-m*-*, .lt-p*-*` — Margens e paddings

## Como Usar

### Opção 1: Componente Completo

Importe o componente de demonstração:

```tsx
import DashboardLegalTechPremium from "./components/DashboardLegalTechPremium";

export default function App() {
  return <DashboardLegalTechPremium />;
}
```

### Opção 2: Classes Avulsas

Use as classes do design system em componentes existentes:

```tsx
<div className="lt-card">
  <div className="lt-card-header">
    <h3 className="lt-card-title">Título do Card</h3>
  </div>
  <p className="lt-text-sm lt-text-secondary">Conteúdo...</p>
</div>
```

### Opção 3: Variáveis CSS

Acesse as variáveis diretamente:

```css
.button {
  background: var(--lt-action);
  color: white;
  border-radius: var(--lt-rounded);
}
```

## Próximos Passos

1. **Integrar com autenticação** — Adaptar o menu lateral às permissões do usuário
2. **Conectar dados reais** — Substituir valores mock por dados da API
3. **Implementar responsividade** — Ajustar breakpoints para mobile/tablet
4. **Adicionar temas** — Criar variações (claro/escuro) mantendo a identidade
5. **Documentar componentes** — Criar Storybook ou documentação similar

---

**Design System**: Legal Tech Premium v1.0  
**Autor**: EJC Development Team  
**Licença**: Proprietária
