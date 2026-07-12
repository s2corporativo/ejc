# NFS-e para o escritório (Betim/MG) — viabilidade e caminho de integração

> Levantamento em 12/07/2026. Betim **aderiu ao Sistema Nacional de NFS-e**
> (SNNFS-e) — Decreto Municipal 51.670; emissão pelo padrão nacional. O sistema
> municipal antigo (GissOnline) fica só para escrituração/guias de ISSQN, não
> para emitir a nota.

## Veredito

Emitir NFS-e pelo EJC em Betim é **viável**. Há dois caminhos:

1. **API oficial do gov (Sefin Nacional)** — REST em produção desde out/2025.
   Base produção `https://sefin.nfse.gov.br/SefinNacional`, homologação
   `https://sefin.producaorestrita.nfse.gov.br/SefinNacional`. Autenticação por
   **mTLS com certificado ICP-Brasil e-CNPJ** (sem token/OAuth — a identidade é
   o certificado no handshake). O documento (DPS — Declaração de Prestação de
   Serviço) vai em **XML assinado com XML-DSig, comprimido GZip + Base64**.
   Trabalho fiscal denso e manutenção contínua a cada nota técnica. Esforço
   ~3–4 semanas + manutenção.

2. **Provedor comercial que abstrai o padrão nacional via JSON** (Nuvem Fiscal
   ~R$360/mês, eNotas ~R$137/mês, PlugNotas por nota, Focus NFe — Betim já
   listado como integrado). Você chama uma API REST JSON simples; o provedor
   cuida de certificado/assinatura/XML/mTLS e das mudanças do padrão. Esforço
   de integração no EJC ~3–5 dias.

**Recomendação para um escritório de 5 advogados: caminho 2 (provedor).** A
mensalidade é irrelevante frente ao custo de manter a integração fiscal oficial
direta. O EJC será construído com uma **interface de provedor abstrata**, então
dá para começar com um provedor e, se um dia o volume justificar, trocar pela
API oficial direta sem reescrever o resto.

## O que só VOCÊ (+ contador) pode providenciar — pré-requisitos

Independente do caminho, a emissão precisa destes itens, que o sistema não pode
inventar:

1. **Certificado digital e-CNPJ ICP-Brasil tipo A1** (arquivo .pfx/.p12) do
   escritório — A1, não A3/token (A3 é impraticável num servidor). ~R$150–250/ano.
2. **Primeiro acesso no Emissor Nacional** (`emissornacional.nfse.gov.br`) com o
   certificado, para parametrização fiscal do prestador.
3. **Definições fiscais com o contador** (mudam como a nota é preenchida):
   - Alíquota de ISS de advocacia em Betim (geral 5%, com 2% em alguns casos —
     confirmar a de advocacia).
   - Se Betim concede **ISS fixo / Sociedade Uniprofissional (SUP)** —
     advocacia pode recolher ISS fixo por profissional em vez de % do
     faturamento (DL 406/68 art. 9º; STJ reafirmou em 2025). **Isso muda a base
     de cálculo da DPS.**
   - Item da lista LC 116/03: **17.14 – Advocacia** (+ código NBS correspondente).
   - Regime (Simples Nacional vs. Presumido) e retenções.
4. **Escolha do provedor** (se caminho 2) e a **chave de API** dele.

## Como será construído no EJC (quando os pré-requisitos existirem)

- Módulo backend gated: `NFSE_ENABLED=false` por padrão, `NFSE_MODO=homologacao`
  primeiro (nunca emite nota real sem configuração explícita), `NFSE_PROVEDOR`,
  credencial/certificado só no `.env` da VPS.
- Serviço com interface de provedor (adapter), models para persistir
  nota/DPS/status/chave de acesso, endpoints emitir/consultar/cancelar (com
  audit log — emissão fiscal é ação sensível), e tela no módulo Financeiro
  (emitir a partir de um honorário/recebível).
- Fluxo: homologação → conferência de uma nota de teste com o contador →
  produção.

## Não verificado (conferir antes de implementar a emissão real)

- Campos exatos/obrigatoriedade da DPS (os PDFs oficiais do gov.br deram 403 no
  ambiente de pesquisa — baixar o "Manual dos Contribuintes – Emissor Público /
  API v1.2 out/2025" no navegador).
- Alíquota de ISS de advocacia e concessão de ISS fixo/SUP **em Betim**
  especificamente (confirmar com contador/Secretaria da Fazenda de Betim).
- Data de obrigatoriedade efetiva vigente para Betim (fontes citam 01/01/2026 e
  01/07/2026).
