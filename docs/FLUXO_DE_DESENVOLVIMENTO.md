# Fluxo de desenvolvimento e auditoria do EJC

Regras canônicas em `docs/GOVERNANCA_IA.md`.

## 1. Escolha do modo de trabalho

### Modo A — auditoria ou revisão somente leitura

Use para diagnóstico, pente fino, revisão de PR, inventário, homologação técnica ou relatório.

Fluxo:

```text
pedido do titular → leitura ampla → buscas/testes/builds → confirmação dos achados → relatório
```

Regras:

- não exige Issue ou branch para começar;
- pode ler todo o repositório e todos os PRs abertos;
- pode examinar arquivos alterados por outras branches;
- pode executar comandos seguros de diagnóstico e testes;
- não altera arquivos, não empurra commit e não opera em produção;
- o relatório deve distinguir fato confirmado, hipótese, limitação e recomendação.

A auditoria pode terminar em chat, comentário de PR, Issue ou documento versionado, conforme a
finalidade.

### Modo B — auditoria corretiva ampla

Use quando o titular autorizar revisão sistêmica com correção, por exemplo: “corrija tudo”,
“faça um pente fino completo”, “homologue e corrija” ou comando equivalente.

Fluxo:

```text
pedido do titular → diagnóstico somente leitura → Issue-guarda-chuva → branch(es)
→ correções relacionadas → testes → PR(s) → revisão independente → homologação
→ merge autorizado
```

Regras:

- o pedido direto do titular autoriza iniciar a auditoria somente leitura;
- a Issue-guarda-chuva deve existir antes da criação da branch de implementação, de qualquer
  alteração em arquivos ou de qualquer commit;
- os achados podem ser agrupados por domínio, dependência, risco ou facilidade de revisão;
- um achado relacionado pode entrar no mesmo PR quando necessário para completar, testar ou
  estabilizar a correção;
- achado sem relação causal é registrado para continuidade, sem interromper o escopo atual;
- mais de um PR pode fechar a mesma Issue-guarda-chuva;
- o relatório final deve mapear cada achado para arquivo, evidência, correção e teste.

### Modo C — desenvolvimento focal

Use para bug, melhoria ou funcionalidade específica.

Fluxo:

```text
pedido/Issue → branch → reprodução → implementação → testes → PR → revisão → homologação
→ autorização do titular → merge → deploy
```

## 2. Antes de escrever código

1. Atualizar a referência da `main` sem alterar a `main` diretamente.
2. Listar PRs abertos e verificar sobreposição real de arquivos e trechos.
3. Reproduzir o problema ou confirmar a necessidade.
4. Definir branch e vínculo com Issue ou Issue-guarda-chuva.
5. Se houver banco: conferir `cd backend && python -m alembic heads` e as reservas existentes.

### Sobreposição com outro PR

Leitura e diagnóstico podem ocorrer em paralelo. Para escrita, arquivo pertencente a PR ativo
não deve ser modificado em outra branch. Escolha uma solução proporcional:

- consolidar as mudanças na mesma branch do PR ativo;
- combinar a ordem de merge e atualizar a branch seguinte depois da integração;
- adiar somente a parte incompatível;
- dividir a entrega por arquivos que não estejam sob alteração concorrente.

Pare quando a escrita pretendida alcançar arquivo de outro PR ativo e ainda não existir uma
estratégia explícita de consolidação ou sequência. Não sobrescreva silenciosamente trabalho
concorrente.

## 3. Implementação

- Implementar o objetivo autorizado e as correções relacionadas necessárias.
- Não usar o rótulo “fora de escopo” para deixar regressão conhecida causada pela própria mudança.
- Registrar toda ampliação material no corpo do PR.
- Criar teste de regressão para bug quando tecnicamente possível.
- Usar fonte oficial, vigência, versão e revisão humana em regra jurídica.
- Evitar massa real, segredo, PII e qualquer acesso à produção.

Validações mínimas devem ser proporcionais ao diff. Exemplos:

```bash
( cd backend && python -m pytest tests -q && python -m ruff check app tests )
( cd frontend && npm test -- --run && npx tsc --noEmit && npm run build )
```

Não é obrigatório rodar toda a suíte antes de qualquer edição pequena, mas o PR deve indicar o
que foi testado, o que não foi e por quê.

## 4. Pull Request

O PR deve:

- apontar para Issue ou Issue-guarda-chuva;
- explicar problema, solução, testes, riscos e rollback;
- declarar sobreposições com outros PRs;
- listar migrations e dependências de ordem de merge;
- anexar evidências de UI quando aplicável;
- permanecer sem merge até revisão e autorização do titular.

Mudança de governança e código funcional pode coexistir quando forem parte da mesma correção
sistêmica. Isso deve ser destacado no PR; a automação emite aviso para revisão reforçada, mas não
reprova automaticamente.

## 5. Revisão

Aplicar `docs/CRITERIOS_DE_ACEITE.md` de forma proporcional ao escopo:

- correção técnica;
- segurança e LGPD;
- validade jurídica;
- fluxo funcional e UX;
- regressão e continuidade.

Revisor pode propor correção, abrir commit em branch própria ou, quando autorizado, corrigir na
branch do PR. O importante é preservar histórico e revisão independente do resultado final.

Mudanças sensíveis envolvendo autenticação, permissões, uploads, CI/CD ou configuração exigem
execução e registro do `security-auditor` antes da finalização e do merge.

## 6. Migrations

Mais de uma branch pode preparar mudança de banco, mas a integração é sequencial:

1. branch atualiza a base;
2. confere o head vigente;
3. ajusta reserva, número e `down_revision`;
4. executa upgrade e valida rollback aplicável;
5. demonstra head único antes do merge.

Migration destrutiva exige backup, plano de rollback e decisão humana registrada.

## 7. Homologação

Mudança funcional deve ser exercitada em stack local ou staging com massa fictícia. Sem staging
permanente, o PR deve dizer claramente que a homologação foi local.

## 8. Ambientes

| Caminho | Uso | Regra |
|---|---|---|
| `/opt/ejc` na VPS | produção | agente não opera diretamente |
| clone/branch de desenvolvimento | escrita e testes | permitido |
| stack local com dados fictícios | homologação | permitido |

Nenhum agente aponta testes para banco de produção ou usa `.env` real sem necessidade operacional
humana e controle específico.
