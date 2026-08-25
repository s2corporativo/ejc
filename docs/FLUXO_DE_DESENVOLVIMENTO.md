# Fluxo de desenvolvimento e auditoria do EJC

Regras canônicas em `docs/GOVERNANCA_IA.md` (v4.0). Este documento descreve o caminho por modo
de trabalho; os portões de verificação são proporcionais ao diff (tabela no `CLAUDE.md`).

## 1. Escolha do modo de trabalho

**Modo A — somente leitura** (diagnóstico, pente fino, revisão de PR, inventário, relatório):

```text
pedido do titular → leitura ampla → buscas/testes/builds → confirmação dos achados → relatório
```

Sem Issue e sem branch para começar; leitura de todo o repositório e PRs abertos, inclusive
arquivos de outras branches; comandos seguros de diagnóstico; nenhuma alteração de arquivo. O
relatório distingue fato confirmado, hipótese, limitação e recomendação, e pode terminar em
chat, comentário de PR, Issue ou documento versionado.

**Modo B — auditoria corretiva ampla** ("corrija tudo", "pente fino completo"):

```text
pedido → diagnóstico somente leitura → Issue-guarda-chuva → branch(es) → correções
→ testes proporcionais → PR(s) → revisão independente → merge conforme §6-A
```

A Issue-guarda-chuva existe antes da primeira escrita. Achados agrupados por domínio, risco ou
facilidade de revisão; achado relacionado entra no mesmo PR quando necessário para completar,
testar ou estabilizar a correção; achado sem relação causal é registrado sem interromper. O PR
final mapeia cada achado para arquivo, evidência, correção e teste.

**Modo C — desenvolvimento focal** (bug, melhoria, funcionalidade):

```text
pedido/Issue → branch → reprodução → implementação → testes proporcionais → PR → gates → merge
```

## 2. Antes de escrever código

1. Atualizar a referência da `main` (sem alterá-la).
2. Listar PRs abertos e verificar sobreposição real de arquivos — arquivo de PR ativo é lock
   lógico: consolidar na branch dele, combinar ordem de merge, dividir por arquivos ou adiar a
   parte incompatível; nunca sobrescrever em silêncio.
3. Reproduzir o problema ou confirmar a necessidade.
4. Definir branch e vínculo com Issue ou Issue-guarda-chuva.
5. Se houver banco: `cd backend && python -m alembic heads` e conferir as reservas.

## 3. Implementação e verificação

- Implementar o objetivo autorizado e as correções relacionadas necessárias. Não usar "fora de
  escopo" para deixar regressão causada pela própria mudança; registrar ampliação material no
  corpo do PR. Teste de regressão para bug quando tecnicamente possível. Fonte oficial,
  vigência e revisão humana em regra jurídica. Sem massa real, segredo, PII ou produção.
- **Verificação proporcional ao diff** (canônico no §6-B da governança; tabela operacional no
  `CLAUDE.md`): durante a iteração, apenas os testes da área em trabalho; o portão completo da
  linha correspondente roda uma vez, antes do push. Docs-only não exige portão técnico —
  declarar no PR. O PR sempre indica o que foi testado, o que não foi e por quê.

```bash
( cd backend && python -m ruff check app && python -m pytest tests -q )   # diff de backend
( cd frontend && npm run lint && npm test -- --run && npm run build )     # diff de frontend
```

## 4. Pull Request

O PR aponta para a Issue (`Closes #NNN`), preenche o template — **que é o relatório da
entrega** — e declara: problema, solução, testes executados e omitidos, riscos, rollback,
sobreposições com outros PRs e migrations com ordem de merge. Evidência de UI quando
aplicável. Nasce draft e é promovido quando a evidência estiver completa; permanece sem merge
até os gates do §6-A (ou, com Actions indisponível, até a decisão do titular sobre a evidência
local). Mudança de governança pode coexistir com código funcional quando for parte da mesma
correção sistêmica — destacada no PR.

## 5. Revisão

Aplicar `docs/CRITERIOS_DE_ACEITE.md` **proporcionalmente ao escopo** — apenas as camadas que
o diff toca. Revisor pode propor correção, abrir commit em branch própria ou, quando
autorizado, corrigir na branch do PR, preservando histórico e independência da revisão.
Área sensível (auth, permissões, uploads, CI/CD, config) exige `security-auditor` registrado
antes do merge.

## 6. Migrations

Integração sequencial: atualizar a base → conferir head vigente → ajustar reserva, número e
`down_revision` → upgrade + rollback validados → head único demonstrado. Migration destrutiva
exige backup, plano de rollback e decisão humana registrada.

## 7. Homologação e ambientes

Mudança funcional é exercitada em stack local ou staging com massa fictícia; sem staging, o PR
declara que a homologação foi local.

| Caminho | Uso | Regra |
|---|---|---|
| `/opt/ejc` na VPS | produção | agente não opera diretamente |
| clone/branch de desenvolvimento | escrita e testes | permitido |
| stack local com dados fictícios | homologação | permitido |

Nenhum agente aponta testes para banco de produção nem usa `.env` real sem controle humano
específico.
