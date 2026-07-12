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

---

## Contrato do adapter — Nuvem Fiscal (provedor padrão, pronto para implementar)

Extraído do OpenAPI/SDK oficial. Interface `NFSeProvider` (emit/get_status/get_pdf/get_xml/cancel); primeiro adapter = `NuvemFiscalProvider`.

**Auth** (OAuth2 client_credentials, token cacheado por `expires_in`):
`POST https://auth.nuvemfiscal.com.br/oauth/token` (form-urlencoded)
`grant_type=client_credentials&client_id=...&client_secret=...&scope=nfse empresa cnpj cep`
→ `Authorization: Bearer <access_token>` nas chamadas. Base da API: `https://api.nuvemfiscal.com.br`. **Um só host** — produção vs. homologação é campo no payload (`ambiente: "homologacao"|"producao"`, `tpAmb: 2|1`).

**Endpoints essenciais:**
- Emitir (modelo nacional/DPS): `POST /nfse/dps` (corpo `NfseDpsPedidoEmissao`) → retorna `{id, status:"processando"}` (ASSÍNCRONO)
- Status: `GET /nfse/{id}` (polling até `autorizada`/`rejeitada`)
- PDF DANFSe: `GET /nfse/{id}/pdf` · XML: `GET /nfse/{id}/xml`
- Cancelar: `POST /nfse/{id}/cancelamento`
- Empresa emitente (1x): `POST /empresas` + `PUT /empresas/{cnpj}/nfse`; certificado A1 (1x): `PUT /empresas/{cnpj}/certificado/upload` (multipart .pfx + senha) — **o certificado vai para o provedor, não para o EJC**.

**Shape mínimo do `POST /nfse/dps`** (prestador vem do cadastro, só CNPJ+regime no payload):
`infDPS`: `tpAmb`, `dhEmi`, `dCompet`, `prest{CNPJ, regTrib}`, `toma{CNPJ/CPF, xNome, end{cMun IBGE, UF, CEP}}`, `serv{locPrest{cLocPrestacao IBGE}, cServ{cTribNac (item 17.14 advocacia), xDescServ}}`, `valores{vServPrest{vServ}, trib{tribMun{tribISSQN, cLocIncid IBGE, pAliq, tpRetISSQN}}}`. Campo `referencia` = chave de idempotência (evita nota duplicada).

**A confirmar na implementação** (via `GET /nfse/cidades/{ibge_betim=3106200}`): formato exato de `cTribNac`/`cTribMun` de Betim para advocacia; disponibilidade de homologação real em Betim; valores dos enums (`tribISSQN`, `tpRetISSQN`, `opSimpNac`).

**Alternativas de adapter** (interface trocável): Focus NFe (host de homologação dedicado, `ref` idempotente, Betim já integrado, Postman público — melhor sandbox), eNotas (mais barato ~R$137, API Key via Basic, modelo mais simples). O fluxo POST→id→polling é ~idêntico entre os três.
