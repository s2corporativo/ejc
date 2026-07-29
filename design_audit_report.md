# 🔍 Auditoria de Design - EJC Workspace Executivo

## 📋 Resumo Executivo

Foram analisados 4 arquivos CSS principais e múltiplos componentes React/TSX.
O design system EJC segue o idioma "Verdelimp" (flat, compacto, premium).

## ✅ Pontos Fortes

1. **Paleta EJC Consistente**
   - Off-white quente (#FAF9F6) + Dourado (#C9A227, #D4AF37, #8F7117, #6F5711)
   - Tema escuro: Grafite/ouro (#14110A, #1C180E)
   - Contraste AA para acessibilidade

2. **Design Flat Premium**
   - Cards: borda 1px + sombra mínima (0 1px 2px)
   - Sem elevação no hover
   - Border-radius: 10-12px cards, 8px botões

3. **Tipografia Inter**
   - Auto-hospedada (LGPD compliant)
   - 15px base, tracking-tight em headings
   - Tabular nums para dados jurídicos

4. **Assinaturas Visuais**
   - Faixa ouro-palha no thead (#F7F1DC)
   - Borda superior 3px em KPIs (#D4AF37)
   - Focus ring dourado

## ⚠️ Inconsistências Encontradas

| Categoria | Problema | Localização | Prioridade |
|-----------|----------|-------------|------------|
| **Bordas** | Múltiplas cores de borda (gray-300, slate-200, --ejc-border) | index.css, Dashboards.tsx | Alta |
| **Inputs** | Alguns com borda visível, outros apenas shadow | site-system.css vs index.css | Média |
| **Botões** | Texto branco sobre #8F7117 tem contraste limítrofe (4.6:1) | index.css .btn-primary | Alta |
| **KPI Icons** | Fundos coloridos variados fogem da paleta EJC | Dashboards.tsx ACCENTS | Baixa |
| **Hover** | Cards mudam border-color para bronze | index.css .card:hover | Baixa |
| **Badges** | Múltiplas variações sem necessidade | index.css .badge-* | Baixa |
| **Dark Mode** | Cobertura incompleta em alguns componentes | Vários | Média |

## 🎯 Recomendações

### Alta Prioridade
1. **Unificar cor de bordas**: Usar apenas `var(--ejc-border)` em todos os cards
2. **Revisar contraste do botão primário**: Considerar texto #FFF5E6 sobre #8F7117
3. **Padronizar inputs**: Remover borda visível, manter apenas shadow inset

### Média Prioridade
4. **Completar dark mode**: Garantir que todos os componentes tenham variante escura
5. **Documentar espaçamentos**: Criar guia de padding/margin padrão

### Baixa Prioridade
6. **Simplificar badges**: Reduzir variações para 4-5 essenciais
7. **Revisar KPI accents**: Alinhar ícones com paleta EJC (ouro/bronze/creme)

## 📐 Especificações do Design Ideal

### Cores
```css
--ejc-bg: #faf9f6          /* Canvas */
--ejc-card: #ffffff        /* Cards */
--ejc-border: #ece8e0      /* Bordas */
--ejc-action: #8f7117      /* Primária */
--ejc-gold: #c9a227        /* Acento */
--ejc-gold-soft: #f7f1dc   /* Fundo suave */
--ejc-bronze: #6f5711      /* Texto escuro */
```

### Cards
- Background: #FFFFFF (light) / #1C180E (dark)
- Border: 1px solid var(--ejc-border)
- Shadow: 0 1px 2px rgba(15, 23, 42, 0.04)
- Radius: 12px (rounded-xl)
- Hover: Sem mudança (flat puro)

### Botões
- Primary: bg #8F7117, text #FFF5E6 (melhor contraste)
- Secondary: bg #FFFFFF, border var(--ejc-border)
- Radius: 8px (rounded-lg)
- Padding: 8px 16px
- Font: 13px, weight 700

### Inputs
- Border: none
- Shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.22)
- Focus: shadow dourado + ring externo
- Radius: 8px
- Padding: 7px 10px
- Font: 13px

### Tabelas
- Thead: bg #F7F1DC, text #3B2F0B
- Th: font 11px, uppercase, tracking-wide
- Tr hover: bg rgba(212, 175, 55, 0.06)
- Border: 1px solid rgba(166, 124, 82, 0.1)

### Tipografia
- Base: 15px Inter
- H1-H4: tracking -0.02em, weight 600-700
- Eyebrow: 10px, uppercase, tracking 0.22em, color #6F5711
- Body: line-height 1.58

### Acessibilidade
- Focus visible: ring 2px rgba(201, 162, 39, 0.7)
- Contraste mínimo: 4.5:1 (AA)
- Scrollbar: 6px thin, custom colors

---

*Relatório gerado automaticamente - Nenhuma alteração foi feita nos arquivos*
