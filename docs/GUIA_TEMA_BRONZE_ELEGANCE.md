# Guia de Implementação: Tema "Bronze & Elegance" para EJC v3.0

## Visão Geral

O tema **"Bronze & Elegance"** foi desenvolvido para transformar a Plataforma Jurídica Empresarial EJC em um sistema de **luxo corporativo**, transmitindo credibilidade, profissionalismo e sofisticação através de uma paleta de cores refinada e tipografia elegante.

## Paleta de Cores

### Cores Primárias (Bronze Brilhante)
- **Bronze Primário**: `#B8860B` (Goldenrod) — Cor principal, transmite confiança e elegância
- **Bronze Escuro**: `#8B6914` — Usado em hover e elementos secundários
- **Bronze Claro**: `#DAA520` — Destaques e acentos
- **Bronze Accent**: `#CD853F` — Variações e elementos especiais

### Cores Secundárias (Champagne & Off-white)
- **Champagne**: `#F5E6D3` — Fundo suave, cards, seções
- **Off-white**: `#FAFAF8` — Fundo principal, limpo e minimalista
- **Cream**: `#FFF8E7` — Alternativa suave
- **Ivory**: `#FFFFF0` — Highlights

### Cores Neutras (Profundidade)
- **Preto Profundo**: `#2C2C2C` — Texto principal
- **Charcoal**: `#3A3A3A` — Texto secundário
- **Cinza Claro**: `#E8E8E8` — Bordas, divisores
- **Cinza Médio**: `#BDBDBD` — Texto desabilitado

## Tipografia

### Fontes
- **Primária**: `Segoe UI`, `Trebuchet MS`, sans-serif (moderna, legível)
- **Accent**: `Georgia`, `Garamond`, serif (elegante, sofisticada)

### Hierarquia de Tamanhos
- **H1**: 2.5rem, Bold, Bronze Primary
- **H2**: 2rem, Semibold, Bronze Dark
- **H3**: 1.5rem, Semibold, Charcoal
- **Body**: 1rem, Regular, Charcoal
- **Small**: 0.875rem, Regular, Gray Medium

## Componentes Principais

### Botões
```html
<!-- Botão Primário (Bronze) -->
<button class="btn btn-primary">Ação Principal</button>

<!-- Botão Secundário (Champagne + Bronze Border) -->
<button class="btn btn-secondary">Ação Secundária</button>

<!-- Botão Outline -->
<button class="btn btn-outline">Ação Terciária</button>
```

### Cards
```html
<div class="card">
  <div class="card-header">
    <h3>Título do Card</h3>
  </div>
  <p>Conteúdo do card com acabamento fino.</p>
</div>
```

### Sidebar
```html
<aside class="sidebar">
  <div class="sidebar-item active">Menu Ativo</div>
  <div class="sidebar-item">Menu Item</div>
</aside>
```

### Header
```html
<header class="header">
  <h1 class="header-title">EJC — Ecossistema Jurídico</h1>
  <div class="header-actions">
    <!-- Ações do header -->
  </div>
</header>
```

## Implementação no Frontend

### 1. Importar o CSS do Tema
```javascript
// Em src/main.jsx ou src/App.jsx
import './styles/theme-bronze-elegance.css';
```

### 2. Usar Tailwind com Configuração Bronze
```bash
# Atualizar tailwind.config.js para usar a configuração bronze
cp frontend/tailwind.config.bronze.js frontend/tailwind.config.js
```

### 3. Aplicar Classes Tailwind
```jsx
// Exemplo de componente com tema Bronze
export function DashboardCard() {
  return (
    <div className="card">
      <div className="card-header">
        <h3>Gestão de Casos</h3>
      </div>
      <p className="text-charcoal-700">
        Centralize todos os seus casos jurídicos em um único lugar.
      </p>
      <button className="btn btn-primary mt-4">
        Criar Novo Caso
      </button>
    </div>
  );
}
```

## Sombras & Efeitos

### Sombras Disponíveis
- `shadow-sm`: Sutil, para cards pequenos
- `shadow-md`: Padrão, para cards normais
- `shadow-lg`: Destaque, para elementos em hover
- `shadow-xl`: Profundo, para modais
- `shadow-bronze`: Especial, com tonalidade bronze

### Transições
- `transition-fast`: 150ms (interações rápidas)
- `transition-normal`: 300ms (padrão)
- `transition-slow`: 500ms (animações suaves)

## Responsividade

O tema foi desenvolvido com mobile-first em mente:

- **Desktop**: Layout completo com sidebar
- **Tablet (768px)**: Ajustes de espaçamento
- **Mobile (480px)**: Stack vertical, botões full-width

## Boas Práticas

1. **Consistência de Cores**: Sempre use as variáveis CSS ou classes Tailwind definidas
2. **Espaçamento**: Utilize o sistema de spacing (xs, sm, md, lg, xl, 2xl, 3xl)
3. **Tipografia**: Mantenha a hierarquia visual com as fontes definidas
4. **Sombras**: Use sombras para criar profundidade, não para escurecer
5. **Transições**: Aplique transições suaves para melhor UX

## Exemplos de Uso

### Dashboard Principal
```jsx
<div className="bg-off-white-100 min-h-screen">
  <header className="header">
    <h1 className="header-title">Dashboard</h1>
  </header>

  <div className="flex gap-lg p-xl">
    <aside className="sidebar w-64">
      {/* Menu lateral */}
    </aside>

    <main className="flex-1">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-lg">
        <div className="card">
          <div className="card-header">
            <h3>Casos Ativos</h3>
          </div>
          <p className="text-4xl font-bold text-bronze-500">24</p>
        </div>
        {/* Mais cards */}
      </div>
    </main>
  </div>
</div>
```

### Formulário Elegante
```jsx
<form className="card max-w-md mx-auto">
  <div className="card-header">
    <h3>Novo Caso</h3>
  </div>

  <div className="mb-lg">
    <label className="label">Título do Caso</label>
    <input type="text" className="input" placeholder="Ex: Ação Anulatória..." />
  </div>

  <div className="mb-lg">
    <label className="label">Área Jurídica</label>
    <select className="input">
      <option>Selecione...</option>
      <option>Civil</option>
      <option>Trabalhista</option>
    </select>
  </div>

  <button type="submit" className="btn btn-primary w-full">
    Criar Caso
  </button>
</form>
```

## Suporte & Manutenção

Para adicionar novas cores ou componentes ao tema:

1. Edite `frontend/src/styles/theme-bronze-elegance.css` para CSS puro
2. Edite `frontend/tailwind.config.bronze.js` para classes Tailwind
3. Mantenha a consistência com a paleta existente
4. Teste em diferentes resoluções

## Versão

- **Tema**: Bronze & Elegance v1.0
- **EJC**: v3.0
- **Data**: Junho 2026
- **Autor**: Manus AI

---

**Nota**: Este tema foi desenvolvido com foco em elegância, profissionalismo e usabilidade. Qualquer modificação deve manter a coerência visual e a experiência do usuário.
