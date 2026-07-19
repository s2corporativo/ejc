# EJC — Design System

**Versão:** Fase 2 do redesign (2026-07-03)
**Fontes da verdade:** `frontend/tailwind.config.js` (tokens), `frontend/src/index.css` (classes utilitárias), `frontend/src/components/UI.tsx` (componentes).

---

## 1. Paleta de cores

### 1.1 Marca — `primary` (bronze)

Cor de ação e identidade (substituiu o remap legado de `blue`). Ações primárias usam **`primary-600`**.

| Token | Hex | Papel |
|---|---|---|
| `primary-50` | `#FAF5EF` | Fundos suaves de destaque (hover de linha, chips) |
| `primary-100` | `#F0E4D2` | Fundo de seleção (`::selection`) |
| `primary-200` | `#E2CBA8` | Rings/bordas de badges bronze |
| `primary-300` | `#CBA877` | Bordas de foco decorativas |
| `primary-400` | `#B98A3C` | Acentos gráficos |
| `primary-500` | `#A6792F` | Acentos gráficos |
| `primary-600` / `DEFAULT` | `#8C6A33` | **Botões e ações primárias** |
| `primary-700` | `#6E5228` | Hover de ação, texto de eyebrow |
| `primary-800`–`950` | `#5A431F`→`#2A1F0C` | Texto sobre fundos claros bronze |

### 1.2 Auxiliares de marca — `bronze` e `gold`

| Token | Hex | Papel |
|---|---|---|
| `bronze` (DEFAULT) | `#8C6A33` | Alias da marca em componentes legados |
| `bronze-dark` | `#6E5228` | Hover |
| `bronze-deep` | `#5A431F` | Texto escuro bronze |
| `bronze-medium` | `#9A7742` | Acentos |
| `bronze-light` | `#C6A158` | Detalhes dourados |
| `bronze-pale` | `#E8D6AE` | Bordas suaves |
| `bronze-50` / `bronze-30` | `#FAF5EF` / `#FDF9F5` | Fundos marfim |
| `gold` (DEFAULT) | `#C6A158` | Destaques premium (`.btn-gold` usa amber) |
| `gold-dark` / `gold-light` | `#9A7742` / `#DBC084` | Variações |
| `gold-700` / `gold-600` / `gold-50` | `#6E5228` / `#8C6A33` / `#FAF5EF` | Escala de apoio |

### 1.3 IA — `ai` (petróleo/teal)

Toda superfície, botão ou badge relacionado a IA usa `ai-*` (substituiu o remap de `violet`/`purple`). Diferencia visualmente o que é gerado por IA (rascunho sujeito a revisão humana — OAB Prov. 205/2021).

| Token | Hex | Papel |
|---|---|---|
| `ai-50` / `ai-100` | `#ECF4F3` / `#D2E7E4` | Fundo de superfícies de IA (`AISurface`, `IANotice`) |
| `ai-200` / `ai-300` | `#A8D0CB` / `#73B0A9` | Bordas/rings de IA |
| `ai-400` / `ai-500` | `#459089` / `#2F7A72` | Acentos |
| `ai-600` / `DEFAULT` | `#266761` | **Botão `variant="ai"`, ícone do bot** |
| `ai-700`–`950` | `#1F534E`→`#0B201E` | Texto sobre fundo claro de IA |

### 1.4 Sidebar / Navy (slate escuro)

| Token | Hex | Papel |
|---|---|---|
| `sidebar` (DEFAULT) | `#0F172A` | Fundo da sidebar |
| `sidebar-light` | `#1E293B` | Blocos elevados na sidebar |
| `sidebar-hover` | `#172033` | Hover de item de menu |
| `sidebar-active` | `#0B111F` | Item ativo |
| `navy` (DEFAULT/900) | `#0F172A` | Títulos serif legados (`text-navy-800` etc.) |
| `navy-950` | `#020617` | Fundo mais escuro |
| `navy-800`/`700`/`600` | `#1E293B`/`#334155`/`#475569` | Texto escuro |
| `navy-100`/`50` | `#F1F5F9`/`#F8FAFC` | Fundos claros |

### 1.5 Status

Escalas completas 50–950 no padrão Tailwind (mesmos hex de emerald/amber/red/sky):

| Família | DEFAULT | Papel |
|---|---|---|
| `success` | `#10b981` | Concluído, pago, favorável, aprovado |
| `warn` (alias `warning`) | `#f59e0b` | Pendente, em revisão, atenção, prazo próximo |
| `danger` (alias `error`) | `#ef4444` | Vencido, atrasado, crítico, exclusão |
| `info` | `#0ea5e9` | Informação neutra, acordo, dicas |

### 1.6 Semânticas de superfície

| Token | Hex | Papel |
|---|---|---|
| `canvas` | `#f7f8fa` | Fundo geral da aplicação |
| `parchment` | `#F1F5F9` | Fundo alternativo (blocos) |
| `ink` / `ink-light` | `#111827` / `#374151` | Texto principal / secundário |
| `muted` | `#6b7280` | Texto de apoio, metadados |
| `border` | `#e5e7eb` | Bordas padrão |

Neutros do dia a dia: escala `slate` nativa do Tailwind (texto `slate-950/900/600/500`, bordas `slate-200/100`, fundos `slate-50`).

---

## 2. Tipografia

### 2.1 Fontes e como são carregadas

- **DM Sans** (sans, padrão) e **Cormorant Garamond** (serif, títulos institucionais) são carregadas via **Google Fonts** com `<link>` no `frontend/index.html` (preconnect + css2), com fallback de sistema declarado no `body` de `index.css`.
- **Mono** (`font-mono`) é **stack de sistema** — nenhuma fonte externa: `ui-monospace, "Cascadia Code", "JetBrains Mono", Consolas, monospace`. Uso: dados processuais (nº CNJ, CPF/CNPJ, valores, códigos).

### 2.2 Escala e papéis

| Classe | Tamanho / linha | Papel |
|---|---|---|
| `text-display` | 2.25rem / 2.6rem | **Display** — números de dashboard (StatCard hero), heros |
| `text-4xl` | 2.25rem / 2.5rem | Título de página grande (legado) |
| `text-3xl` | 1.75rem / 2.1rem | H1 de página (`PageHeader` em md+) |
| `text-2xl` | 1.375rem / 1.9rem | H1 de página (mobile), valores de StatCard |
| `text-xl` / `text-lg` | 1.1875 / 1.0625rem | **Heading** — títulos de seção/modal |
| `text-base` | 0.9375rem / 1.6rem | **Body** — texto corrido |
| `text-sm` | 0.8125rem / 1.25rem | Body compacto (tabelas, formulários, cards) |
| `text-xs` | 0.75rem / 1.125rem | Labels, subtítulos |
| `text-caption` | 0.7rem / 1rem | **Caption** — metadados, legendas, timestamps |
| `text-2xs` | 0.65rem / 1rem | Micro-labels (badges, eyebrow) |
| `font-mono` | — | **Mono** — nº CNJ, CPF/CNPJ, valores, texto a digitar em confirmações |

Pesos disponíveis: `light 300`, `normal 400`, `medium 500`, `semibold 600`, `bold 700` — a Inter variável carregada em `fonts.css` cobre 300–700, e 700 é o peso padrão de botões e títulos no idioma atual (acima de 700, ex.: `extrabold`, não carregado). Tracking: `tightest`→`widest` (eyebrow usa `tracking-[0.22em]` via classe `.eyebrow`).

---

## 3. Espaçamento, sombras e animações

- **Espaçamento**: escala padrão do Tailwind. Padrões da casa (idioma flat/compacto): padding de card `p-4`/`p-5`, gap entre blocos de página `space-y-5`, raio `rounded-xl` = 12px (cards; KPI cards 10px com borda superior de 3px na cor do indicador) e `rounded-lg` = 8px (botões/inputs), modais `rounded-2xl`.
- **Sombras** (tailwind.config.js): uso mínimo — cards e superfícies usam borda 1px + `0 1px 2px` sutil; `shadow-float` fica reservada a modais/popovers. Sem elevação/`translateY` no hover.
- **Animações**: `animate-fade-in` (0.25s, overlays), `animate-rise` (0.3s, entrada de página — `<div className="space-y-5 animate-rise">`), `animate-pop` (0.18s, painéis de modal), `animate-slide-in-right` (0.25s, Drawer), `animate-pulse` (Skeleton).
- **Classes utilitárias do index.css**: `.card`, `.section-card`, `.btn-primary|-gold|-ghost|-secondary|-outline|-danger`, `.input`, `.label`, `.badge-*`, `.table`, `.modal-backdrop`, `.eyebrow`, `.hero-blue`.

---

## 4. Catálogo de componentes (`src/components/UI.tsx`)

Todos importados de `../components/UI`. Utilitário `cn(...classes)` concatena classes condicionalmente.

### Ações e navegação

| Componente | Props principais | Exemplo |
|---|---|---|
| `Button` | `variant: "primary"\|"secondary"\|"ghost"\|"danger"\|"ai"`, `size: "sm"\|"md"\|"lg"\|"icon"`, `icon`, + atributos de `<button>` | `<Button icon={<Plus className="h-4 w-4" />}>Novo caso</Button>` |
| `Tabs` | `items: {value, label, icon?}[]`, `value`, `onChange` | `<Tabs items={abas} value={aba} onChange={setAba} />` |
| `Dropdown` | `label`, `children` (usa `<details>`) | `<Dropdown label="Ações">…</Dropdown>` |
| `Tooltip` | `label`, `children` | `<Tooltip label="Editar"><Button size="icon" … /></Tooltip>` |

### Superfícies

| Componente | Props | Exemplo |
|---|---|---|
| `Card` | `className` | `<Card className="p-4">…</Card>` |
| `SectionCard` | `title?`, `subtitle?`, `actions?` | `<SectionCard title="Prazos" actions={<Button size="sm">Ver todos</Button>}>…</SectionCard>` |
| `StatCard` | `label`, `value`, `subtitle?`, `icon?`, `tone?`, `trend?: "up"\|"down"` | `<StatCard label="Casos ativos" value={42} icon={<Scale />} tone="green" />` |
| `PageHeader` | `title`, `subtitle?`, `eyebrow?`, `actions?` | `<PageHeader title="Casos" subtitle="…" actions={<Button>Novo</Button>} />` |

### Badges

| Componente | Props | Exemplo |
|---|---|---|
| `Badge` | `tone: "slate"\|"blue"\|"green"\|"amber"\|"red"\|"purple"` | `<Badge tone="green">pago</Badge>` |
| `StatusBadge` | `value?: string` — mapeia status→tom (ativo/pago→verde, pendente→âmbar, vencido→vermelho, ia→ai, arquivado→slate…) | `<StatusBadge value={caso.status} />` |
| `PriorityBadge` | `value?: string` (alta/critica→vermelho, media→âmbar) | `<PriorityBadge value={prazo.prioridade} />` |
| `ConfidenceBadge` | `value?: number` (0–100; ≥80 verde, ≥60 âmbar, <60 vermelho) | `<ConfidenceBadge value={87} />` |

### Formulários

| Componente | Props | Exemplo |
|---|---|---|
| `FieldLabel` | `required?` | `<FieldLabel required>Título</FieldLabel>` |
| `Input` / `Select` / `Textarea` | atributos nativos (classe `.input` aplicada) | `<Input value={v} onChange={…} />` |
| `SearchBar` | `value`, `onChange(string)`, `placeholder?` | `<SearchBar value={q} onChange={setQ} />` |
| `FilterBar` | `children`, `onClear?` | `<FilterBar onClear={limpar}><Select … /></FilterBar>` |

### Sobreposições (novos na Fase 2 em **negrito**)

| Componente | Props | Exemplo |
|---|---|---|
| `Modal` | `open`, `onClose`, `title`, **`size?: "sm"\|"md"\|"lg"\|"xl"`**, **`footer?`**, `wide?` (legado = `xl`). **Fecha com Esc e clique no overlay.** | `<Modal open={aberto} onClose={fechar} title="Novo caso" size="lg" footer={<Button onClick={salvar}>Salvar</Button>}>…</Modal>` |
| **`ConfirmModal`** | `open`, `onClose`, `onConfirm`, `title?`, `message?`, `variant?: "danger"\|"primary"`, `typeToConfirm?` (exige digitar o texto exato), `confirmLabel?`, `cancelLabel?`, `loading?` | `<ConfirmModal open={c} onClose={f} onConfirm={excluir} title="Excluir caso" message="Move para a lixeira." typeToConfirm={caso.titulo} />` |
| **`Drawer`** | `open`, `onClose`, `title`, `width?: "sm"\|"md"\|"lg"`, `footer?`. Slide-in pela direita, Esc/overlay fecham. | `<Drawer open={ajuda} onClose={f} title="Ajuda — Casos">…</Drawer>` |

### Feedback e estados

| Componente | Props | Exemplo |
|---|---|---|
| **`Alert`** | `variant: "info"\|"success"\|"warning"\|"danger"`, `title?`, `children` (ícone lucide automático) | `<Alert variant="warning" title="Prazo próximo">Vence em 2 dias úteis.</Alert>` |
| `EmptyState` | `title?`, `message?`, `icon?`, `action?` | `<EmptyState title="Nenhum caso" message="Crie o primeiro." action={<Button>Novo</Button>} />` |
| `Empty` | `message`, `icon?` (atalho de EmptyState — manter para compatibilidade) | `<Empty message="Nenhum registro encontrado" />` |
| `Spinner` | — | `{loading ? <Spinner /> : …}` |
| `Skeleton` | `className?` (padrão `h-4 w-full`) | `<Skeleton className="h-24" />` |

### Tabela

| Componente | Props | Observação |
|---|---|---|
| `Table` | `children`, `className?` | Wrapper com borda arredondada + `overflow-x-auto`; estilos de `.table` (cabeçalho slate, hover bronze) |
| **`THead`** | `children`, `className?` | `<thead>` semântico |
| **`TR`** | `zebra?: boolean` (padrão `true` — zebra sutil `even:bg-slate-50/40`; desligar no cabeçalho), + atributos de `<tr>` | |
| **`TH`** / **`TD`** | atributos nativos | Estilo vem da classe `.table` |

```tsx
<Table>
  <THead>
    <TR zebra={false}>
      <TH>Cliente</TH>
      <TH>Status</TH>
    </TR>
  </THead>
  <tbody>
    {itens.map((c) => (
      <TR key={c.id}>
        <TD>{c.nome}</TD>
        <TD><StatusBadge value={c.status} /></TD>
      </TR>
    ))}
  </tbody>
</Table>
```

### IA e Visual Law

| Componente | Props | Exemplo |
|---|---|---|
| `IANotice` | `children?` (padrão: aviso de revisão humana) | `<IANotice />` |
| `AISurface` | `title?`, `subtitle?`, `actions?` — superfície `ai-*` com ícone de bot | `<AISurface title="Análise estratégica">…</AISurface>` |
| `VisualLawDocument` | `title`, `subtitle?`, `meta: {label, value}[]` — documento formatado Visual Law | `<VisualLawDocument title="Parecer" meta={[{label:"Processo", value:cnj}]}>…</VisualLawDocument>` |

Fora do UI.tsx: `components/Markdown.tsx` (`<Markdown source={…} className? />` — parser seguro em elementos React), `components/ai/AIResponse.tsx` (Markdown + badge de confiança + aviso OAB), `components/Toast.tsx` (toasts via CustomEvent), `components/CommandPalette.tsx` (Ctrl+K).

### Formatadores

`fmtMoney(v?: number)` → `R$ 1.234,56` | `fmtDate(d?: string)` → `dd/mm/aaaa` (ambos retornam `—` para nulo).

---

## 5. Regras de uso

1. **Texto vindo de IA ou de campo livre do usuário SEMPRE via `<Markdown source={…} />` ou `<AIResponse>`. NUNCA `dangerouslySetInnerHTML`** (a única ocorrência do projeto, em MemoriaInstitucional.tsx, foi eliminada na Fase 2 — não reintroduzir).
2. **Status/risco/urgência/área sempre com badge** (`StatusBadge`/`PriorityBadge`/`Badge`/`ConfidenceBadge`) — Visual Law: informação de estado é visual, não só texto.
3. **Ações primárias em `primary-600`** (`Button variant="primary"` ou `.btn-primary`); ações destrutivas em `danger` com `ConfirmModal` (exclusões críticas usam `typeToConfirm`).
4. **Superfícies e ações de IA sempre em `ai-*`** (`Button variant="ai"`, `AISurface`, `IANotice`) — o usuário precisa distinguir à primeira vista o que é rascunho de IA.
5. **Dark mode via classe** (`darkMode: "class"` + hook `useTheme`) — nunca `@media (prefers-color-scheme)`; ao criar componente novo, testar com a classe `dark` aplicada.
6. **Estados obrigatórios em toda tela com dados**: loading (`Spinner`/`Skeleton`), vazio (`Empty`/`EmptyState` — "Nenhum registro encontrado"), erro (`Alert variant="danger"` ou toast).
7. **Todo texto em pt-BR**; datas com `fmtDate`, moeda com `fmtMoney`; dados processuais (CNJ, CPF/CNPJ) em `font-mono`.
8. **Não regressão**: não remover/renomear componentes, props ou exports; apenas adicionar (props novas sempre opcionais).
9. Formulários: bloquear duplo submit (`disabled={salvando}`), validação com mensagem por campo.
10. Mobile-first: grids `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`; tabelas sempre dentro de `Table` (overflow-x-auto).

---

## 6. Como adicionar uma tela nova

Esqueleto padrão (segue as 10 páginas principais):

```tsx
import { useEffect, useState, useCallback } from "react";
import { Plus } from "lucide-react";
import api from "../lib/api";
import {
  PageHeader, FilterBar, SearchBar, Select, Button,
  Card, Table, THead, TR, TH, TD,
  Spinner, Empty, Alert, StatusBadge, fmtDate,
} from "../components/UI";

interface Item { id: string; nome: string; status: string; created_at: string }

export default function MinhaTela() {
  const [itens, setItens] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro("");
    try {
      const { data } = await api.get("/meu-endpoint", { params: { q, status } });
      setItens(data);
    } catch {
      setErro("Não foi possível carregar os registros.");
    } finally {
      setLoading(false);
    }
  }, [q, status]);

  useEffect(() => { carregar(); }, [carregar]);

  return (
    <div className="space-y-5 animate-rise">
      {/* 1. Cabeçalho */}
      <PageHeader
        title="Minha Tela"
        subtitle="Descrição curta do módulo"
        actions={<Button icon={<Plus className="h-4 w-4" />}>Novo</Button>}
      />

      {/* 2. Filtros */}
      <FilterBar onClear={() => { setQ(""); setStatus(""); }}>
        <div className="min-w-[220px] flex-1"><SearchBar value={q} onChange={setQ} /></div>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40">
          <option value="">Todos os status</option>
        </Select>
      </FilterBar>

      {/* 3. Conteúdo — sempre com os 3 estados */}
      {erro && <Alert variant="danger" title="Erro">{erro}</Alert>}
      {loading ? (
        <Spinner />
      ) : itens.length === 0 ? (
        <Empty message="Nenhum registro encontrado" />
      ) : (
        <Table>
          <THead>
            <TR zebra={false}><TH>Nome</TH><TH>Status</TH><TH>Criado em</TH></TR>
          </THead>
          <tbody>
            {itens.map((i) => (
              <TR key={i.id}>
                <TD>{i.nome}</TD>
                <TD><StatusBadge value={i.status} /></TD>
                <TD className="font-mono text-caption">{fmtDate(i.created_at)}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
```

Checklist antes de abrir PR de tela nova:

- [ ] Rota registrada em `App.tsx` com lazy loading e guard de papel se necessário (`RoleOnly`)
- [ ] Loading + vazio + erro implementados
- [ ] pt-BR em todos os textos; `fmtDate`/`fmtMoney` nos dados
- [ ] Responsivo em 375px (tabela dentro de `Table`, grids com breakpoints)
- [ ] Conteúdo de IA/campo livre via `Markdown`/`AIResponse` (zero `dangerouslySetInnerHTML`)
- [ ] `npx tsc --noEmit` limpo
