# Roteiro de Teste Real do EJC

Este roteiro deve ser executado em homologação com dados fictícios antes de liberar mudanças relevantes.

## Dados fictícios mínimos

- Cliente pessoa física.
- Cliente pessoa jurídica.
- Caso cível ou consumidor.
- Caso trabalhista.
- Processo com número fictício.
- Documento normal.
- Documento confidencial.
- Honorário lançado.
- Despesa lançada.
- Usuários com perfis diferentes.

## Fluxo 1 — Cliente e caso

1. Entrar como admin ou socio.
2. Criar cliente fictício.
3. Criar caso vinculado ao cliente.
4. Atribuir advogado responsável.
5. Entrar como advogado responsável e confirmar acesso.
6. Entrar como advogado sem vínculo e confirmar bloqueio quando aplicável.

## Fluxo 2 — Documentos

1. Enviar documento normal vinculado ao caso.
2. Confirmar que o documento aparece no caso correto.
3. Enviar documento confidencial vinculado ao caso.
4. Confirmar que perfil sem permissão não acessa o documento confidencial.
5. Confirmar que download sensível gera auditoria quando aplicável.
6. Confirmar que documento não aparece para cliente externo se não estiver liberado.

## Fluxo 3 — Prazos e tarefas

1. Criar prazo no caso.
2. Criar tarefa vinculada ao caso.
3. Verificar dashboard, agenda e listagem.
4. Testar alteração de status.
5. Testar bloqueio para perfil sem permissão.

## Fluxo 4 — Financeiro

1. Lançar honorário.
2. Lançar despesa.
3. Acessar financeiro como socio/admin/financeiro.
4. Tentar acessar financeiro como estagiario e advogado sem permissão.
5. Testar exportação financeira.
6. Confirmar que dados societários não aparecem para perfil indevido.

## Fluxo 5 — IA jurídica

1. Solicitar análise de caso com documento fictício.
2. Verificar se resposta indica revisão humana.
3. Verificar se fontes são registradas quando houver RAG.
4. Confirmar que IA não acessa caso fora do escopo do usuário.
5. Confirmar registro de log de uso quando aplicável.

## Fluxo 6 — Portal do cliente

1. Criar usuário cliente externo vinculado ao cliente.
2. Entrar como cliente externo.
3. Confirmar que visualiza apenas seus próprios casos.
4. Confirmar que não acessa rotas internas.
5. Confirmar que não visualiza estratégia jurídica interna.
6. Confirmar que só visualiza documentos normais/liberados.

## Resultado esperado

Cada fluxo deve gerar um relatório simples:

- Passou.
- Falhou.
- Rota quebrada.
- Permissão incorreta.
- Erro visual.
- Erro backend.
- Necessita correção antes do merge.
