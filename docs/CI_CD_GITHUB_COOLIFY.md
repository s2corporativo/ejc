# CI/CD canônico — GitHub Actions + Coolify

Data de adoção: 2026-09-28.

## Objetivo

Migrar o EJC de Woodpecker self-hosted para uma esteira com separação rígida entre validação e produção:

1. Pull Requests e pushes na `main` são validados em runners GitHub-hosted `ubuntu-latest`.
2. Código de PR nunca executa na VPS de produção.
3. Deploy passa a ser responsabilidade do Coolify, conectado somente à branch `main`.
4. Produção nunca recebe deploy de branch de PR.
5. O Woodpecker permanece somente como fallback temporário até o primeiro ciclo verde do GitHub Actions + prova de deploy/rollback no Coolify.

## Critérios para promoção definitiva

- GitHub Actions inicia e conclui no SHA exato do PR;
- nenhum job de `pull_request` usa runner self-hosted;
- todos os gates obrigatórios equivalentes ao CI anterior passam;
- Coolify instalado e acessível;
- Coolify configurado com proxy `Custom (None)` enquanto o Nginx do host ocupar 80/443;
- repositório GitHub conectado por GitHub App com acesso apenas a `s2corporativo/ejc`;
- aplicação de homologação implantada a partir de `main`;
- healthcheck aprovado;
- rollback para a imagem/deploy anterior comprovado;
- somente após essas evidências o Woodpecker pode ser desativado/removido.

## Rollback

Enquanto a migração não for homologada, não alterar o fluxo produtivo atual. Em caso de falha do novo CI ou Coolify:

- interromper promoção do novo fluxo;
- manter o SHA de produção vigente;
- usar o mecanismo de deploy já homologado;
- não desabilitar Woodpecker antes da equivalência comprovada.

## Segurança

A VPS não deve possuir runner de Pull Request. Coolify recebe apenas a branch `main` já integrada. Secrets de produção permanecem fora do Git e não são disponibilizados a workflows de PR.
