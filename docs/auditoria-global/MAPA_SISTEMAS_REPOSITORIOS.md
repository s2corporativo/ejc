# Mapa Sistemas ↔ Repositórios

**Snapshot:** 2026-08-24 (BRT)

Este mapa distingue nome de negócio, implementação técnica e ambiente publicado. Nenhuma correspondência foi inventada apenas por similaridade nominal.

| Sistema / referência de negócio | Repositório técnico verificável | Evidência / leitura | Produção documentada | Estado do mapeamento |
|---|---|---|---|---|
| EJC / Ecossistema Jurídico Clovis | `s2corporativo/ejc` | `CLAUDE.md`, routers, módulos, docs | `https://ejc.depaulateixeira.adv.br` | confirmado |
| S2 / licitações / cotações / propostas | `s2corporativo/s2licit` | manifesto `orcamento-fornecedores`, docs de domínio | `https://s2.s2corporativo.com.br` | confirmado |
| LicitaCore | não há repo com esse nome/termo indexado | busca global sem ocorrência de `LicitaCore` | — | tratar como referência de negócio do S2 até evidência contrária |
| Verdelimp ERP | `s2corporativo/verdelimpclaude` | package `verdelimp-erp`, docs/issues | evidências divergentes: histórico `verdelimp.s2corporativo.com.br`; issue atual aponta `erp.verdelimp.com.br` | repo confirmado; domínio precisa reconciliação operacional |
| CuidarVet | `s2corporativo/cuidar-vet-plataforma` | manifesto, roadmap, importação NuvemVet | URL canônica não comprovada pela evidência acessível | repo confirmado; produção não certificada |
| Anifarm / compêndio veterinário | `s2corporativo/anifarm` | package `compendio-dashboard` | não comprovada | confirmado como projeto ativo |
| Anifarm legado | `s2corporativo/Anifarm-` | metadata GitHub | não aplicável | arquivado |
| AcioneJus | integrado em `s2corporativo/ejc` | referências em DPT360, intake, monitor/IA defensiva e documentação | site externo não mapeado a repo próprio nesta instalação | integração confirmada; repo autônomo não encontrado |
| De Paula Teixeira / DPT | integrado em `s2corporativo/ejc` | branding, DPT360, docs e domínio EJC | domínio EJC documentado; site institucional próprio não mapeado a repo separado | integração confirmada; repo autônomo não encontrado |
| Portfólio / sistema de máquinas | não há repo autônomo encontrado | termos de equipamentos/retroescavadeira aparecem no Verdelimp | não comprovada | tratar como funcionalidade/negócio Verdelimp até evidência contrária |
| Fitness Tracker | `s2corporativo/clovis-fitness-tracker` | metadata e branches | não comprovada | confirmado |
| Framework de agentes OpenAI | `s2corporativo/openai-agents-python` | metadata GitHub confirma fork | homepage do upstream | dependência/fork, não sistema proprietário |
| Skills Manus | `s2corporativo/skills-manus` | metadata GitHub | não aplicável | auxiliar |

## Dependências e relações relevantes

### EJC ↔ Verdelimp

Há evidência histórica de uso temporário do runner/infra do EJC como ponte de deploy do Verdelimp. O bridge foi concebido como temporário e há PR posterior para removê-lo. Isso deve permanecer desacoplado: EJC não é deployment host lógico do Verdelimp.

### EJC ↔ AcioneJus / DPT

AcioneJus e De Paula Teixeira aparecem como integrações/módulos dentro do EJC. Não foi encontrado repositório separado acessível para os sites durante a descoberta global. Qualquer site implantado fora desta instalação deve ser inventariado quando o repositório/conta correspondente for conectado.

### S2 ↔ portais externos

S2 integra ou planeja integrar PNCP, Compras.gov.br, FUNDEP, FUNARBE, FIEMG, Compras MG e outros. CAPTCHA/2FA e confirmação final permanecem como gates humanos; credenciais externas não são parte do repositório.

### CuidarVet ↔ NuvemVet

O repositório contém frente de importação/substituição do NuvemVet. Importação definitiva é operação de dados, não simples merge de código: exige `DATABASE_URL` correta, pré-validação, reconciliação e autorização operacional.

## Estado publicado: regra de evidência

Nesta auditoria, `main`, PR aberta, branch atualizada e produção são estados distintos.

- **EJC:** produção documentada, mas deploy está bloqueado por backup/offsite e runner/CI; há commits integrados ainda não certificados.
- **S2:** domínio oficial documentado; homologações externas de portais/fornecedores continuam pendentes.
- **Verdelimp:** há evidência histórica de deploy e health HTTP 200, mas a documentação atual de domínio diverge e a issue de produção exige DNS/credenciais/health para certificação.
- **CuidarVet:** nenhum domínio canônico foi comprovado no repositório acessível; roadmap ainda exige homologação antes de substituir NuvemVet.

A tentativa de validação HTTP externa desta sessão ficou inconclusiva por limitação de resolução DNS no ambiente de consulta. Isso **não** foi interpretado como indisponibilidade dos serviços.
