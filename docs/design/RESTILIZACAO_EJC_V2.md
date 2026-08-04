# Restilização EJC v2 — reinício controlado

## Decisão

A primeira tentativa de refatoração visual foi encerrada sem merge. Esta frente começa novamente a partir da `main`, sem herdar CSS, componentes ou decisões visuais do PR anterior.

## Objetivo visual

Reproduzir com fidelidade estrutural o conceito aprovado para o dashboard do EJC:

- identidade premium em preto, branco e dourado;
- sidebar escura com logomarca original em área branca própria;
- cabeçalho superior com hora, data, versículo/frase diária, WhatsApp, e-mail, IA do Escritório e perfil autenticado;
- calendário semanal na lateral;
- dashboard compartilhado sem indicadores financeiros;
- cards, agenda, andamentos, distribuição por área, status de processos e atalhos rápidos com dados reais;
- funcionamento completo em desktop, tablet e celular.

## Método obrigatório

1. Auditar a arquitetura atual da `main` antes de alterar qualquer tela.
2. Criar o novo layout em componentes próprios e isolados.
3. Não usar uma folha global de sobrescritas para simular fidelidade visual.
4. Não reaproveitar o CSS específico do PR encerrado.
5. Preservar autenticação, RBAC, rotas, APIs, RAG, notificações, privacidade e regras de negócio.
6. Implementar primeiro o shell e o dashboard; só depois propagar o padrão aos módulos.
7. Validar visualmente em 1440, 1366, 1024, 768, 390 e 360 px.
8. Não usar dados fictícios permanentes nem exibir zero quando uma API falhar.

## Critérios de aceite da primeira etapa

- shell novo construído por composição de componentes, não por repintura global;
- logo original preservada e destacada;
- proporções da sidebar, cabeçalho e grid próximas da referência;
- contatos e IA compactos e funcionais;
- calendário semanal integrado;
- dashboard sem conteúdo financeiro;
- build, typecheck e testes do frontend aprovados;
- evidências visuais anexadas ao PR antes do merge.
