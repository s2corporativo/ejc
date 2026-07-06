# Checklist de Release do EJC

Use este checklist antes de transformar uma PR em pronta para merge.

## 1. Escopo

- [ ] A PR tem objetivo claro.
- [ ] Não mistura correção crítica com redesign amplo.
- [ ] Não cria módulo duplicado.
- [ ] Informa arquivos e módulos afetados.

## 2. Segurança e permissões

- [ ] Backend valida autenticação.
- [ ] Backend valida perfil autorizado.
- [ ] Backend valida ownership por caso, cliente ou usuário.
- [ ] Frontend esconde rotas e menus incompatíveis com o perfil.
- [ ] Cliente externo permanece confinado ao portal.
- [ ] Dados financeiros não aparecem para perfis indevidos.
- [ ] Documentos confidenciais não aparecem para perfis indevidos.

## 3. Banco e migrations

- [ ] Toda alteração de schema tem migration Alembic.
- [ ] `alembic upgrade head` passa em banco limpo.
- [ ] Não há DROP sem justificativa, backup e janela de manutenção.
- [ ] Não há drift de schema.

## 4. Testes técnicos

- [ ] Backend pytest passa.
- [ ] Frontend typecheck passa.
- [ ] Frontend build passa.
- [ ] Testes com Postgres real passam quando houver banco envolvido.
- [ ] Testes de row-level passam quando houver dados sensíveis.

## 5. Teste real de usuário

- [ ] Login com perfil autorizado.
- [ ] Login com perfil sem autorização.
- [ ] Fluxo de cliente/caso/documento testado quando aplicável.
- [ ] Exportações testadas quando aplicável.
- [ ] IA testada com revisão humana quando aplicável.
- [ ] Portal do cliente testado quando aplicável.

## 6. Auditoria e conformidade

- [ ] Ações sensíveis geram log.
- [ ] Download de documento sensível gera trilha.
- [ ] Uso de IA registra fontes e usuário quando aplicável.
- [ ] Não há segredo ou credencial versionada.

## 7. Decisão final

- [ ] CI aprovado no último commit da branch.
- [ ] Branch sincronizada com main.
- [ ] Pendências críticas resolvidas.
- [ ] PR não está em draft.
- [ ] Merge aprovado de forma consciente.
