---
name: integrador-google-search-console
description: >
  Especialista em configuração, diagnóstico e operação do Google Search Console para os sites do ecossistema Dr. Clovis: acionejus.com.br e depaulateixeira.adv.br (ambos com indexação pendente). Cobre: verificação de propriedade, submissão de sitemap, análise de cobertura de índice, correção de erros de rastreamento, relatórios de desempenho de keywords, Core Web Vitals, rich results e integração com Google Analytics 4. Aciona em: "search console", "indexação do site", "site não aparece no Google", "submeter sitemap", "verificar site Google", "GSC", "rastreamento Google", "erros de indexação", "cobertura de índice", "keywords orgânicas", "cliques orgânicos", "CTR orgânico", "sitemap.xml", "robots.txt", "Core Web Vitals", "rich results", "schema markup Google".
---

# INTEGRADOR GOOGLE SEARCH CONSOLE

## Sites Prioritários
1. **acionejus.com.br** — React SPA, sitemap.xml presente, Search Console pendente
2. **depaulateixeira.adv.br** — Site do escritório, indexação pendente

## Passo a Passo: Verificação e Configuração Inicial

### Para acionejus.com.br:
1. Acesse: https://search.google.com/search-console
2. Clique em "Adicionar propriedade" → "Prefixo de URL"
3. Insira: `https://acionejus.com.br/`
4. Método de verificação recomendado: **tag HTML** (inserir no `<head>` do index.html)
   ```html
   <meta name="google-site-verification" content="[CODE]" />
   ```
5. Após verificar → Sitemaps → Adicionar: `https://acionejus.com.br/sitemap.xml`
6. Aguardar 48-72h para dados aparecerem

### Alternativa sem editar código (se acesso ao servidor for difícil):
- Método DNS: adicionar registro TXT no Hostinger apontando para o domínio
- Método Google Analytics: se GA4 já estiver instalado

## Diagnóstico de Problemas Comuns

### SPA React (acionejus.com.br):
- **Problema:** Googlebot lê HTML estático (sem JS) → vê título genérico em todas as páginas
- **Solução:** Confirmar implementação do useSEO hook + verificar no GSC "Inspecionar URL" se Google renderiza o JS
- **Ferramenta:** URL Inspection Tool → ver versão renderizada vs HTML bruto

### Erros de Cobertura:
| Erro | Causa | Solução |
|---|---|---|
| "Excluída por tag noindex" | Meta robots errada | Verificar `<meta name="robots">` |
| "Rastreada, não indexada" | Conteúdo duplicado ou thin | Adicionar conteúdo único por página |
| "Erro 404" | URL quebrada no sitemap | Atualizar sitemap.xml |
| "Redirecionamento" | URL muda antes de indexar | Verificar canonical + redirects |

## Relatórios Essenciais a Monitorar (Semanalmente)

### 1. Desempenho de Busca:
- Cliques, impressões, CTR, posição média por keyword
- Filtrar por página para ver quais páginas ranqueiam
- Identificar keywords na posição 8-20 (oportunidade de melhoria com conteúdo)

### 2. Cobertura de Índice:
- Quantas URLs indexadas vs total do sitemap
- Erros bloqueando indexação

### 3. Core Web Vitals:
- LCP (carregamento) < 2.5s
- INP (interação) < 200ms
- CLS (estabilidade visual) < 0.1

### 4. Rich Results:
- Verificar se Schema JSON-LD está sendo lido corretamente
- FAQPage, Organization, LocalBusiness

## Keywords Prioritárias por Site

### acionejus.com.br:
- "nome sujo como limpar" (alto volume)
- "negativação indevida o que fazer" (transacional)
- "juizado especial online" (transacional)
- "cobrança indevida como reclamar" (informacional)
- "produto não entregue mercado livre" (específico)
- "juizado especial betim mg" (local)
- "juizado especial belo horizonte" (local)

### depaulateixeira.adv.br:
- "advogado trabalhista betim mg"
- "advogado licitações betim"
- "advogado direito do consumidor betim"
- "escritório advocacia betim mg"

## Integração com GA4
Vincular Search Console ao GA4 para ver:
- Quais keywords orgânicas geram conversões reais
- Caminho do usuário de orgânico até lead/venda
- Taxa de conversão por landing page orgânica

## Ações Imediatas (Pendentes)
- [ ] acionejus.com.br: verificar propriedade no GSC
- [ ] acionejus.com.br: submeter sitemap.xml
- [ ] depaulateixeira.adv.br: criar e verificar propriedade
- [ ] Ambos: criar Google Meu Negócio (Betim/MG)
- [ ] Ambos: instalar GA4 e vincular ao GSC
