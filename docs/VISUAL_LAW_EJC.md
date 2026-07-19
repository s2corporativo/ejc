# Visual Law no EJC

## Objetivo

Aplicar Visual Law de forma consistente na interface e nos documentos gerados pelo EJC, sem alterar o teor jurídico das peças.

Visual Law, neste projeto, significa organizar o conteúdo jurídico com melhor hierarquia visual, resumos de controle, metadados claros, alertas de revisão e estrutura de leitura mais amigável.

## Onde aplicar

### Interface do sistema

- Pré-visualização de peças jurídicas.
- Impressão de peças pela tela.
- Cards de documentos, validações, revisões e status.
- Fluxos de criação de petições, contratos, notificações e pareceres.

### Documentos gerados

- PDF final/protocolo: deve usar o tema central `backend/app/services/visual_law_theme.py`.
- DOCX editável: deve manter formatação jurídica editável, mas incluir quadro de controle Visual Law no início.
- Relatórios e demonstrativos: devem usar capa, metadados, alertas e blocos de síntese.

## Regras

1. Visual Law não pode alterar tese, fundamento, pedido ou conteúdo jurídico.
2. Visual Law deve melhorar leitura, navegação e controle.
3. Todo documento assistido por IA deve manter aviso de revisão humana.
4. Exportação final deve preservar gates de validação jurídica e revisão humana.
5. O padrão visual deve usar a identidade De Paula Teixeira: marrom, bronze, dourado e superfícies claras.

## Componentes do padrão

- Capa ou cabeçalho editorial.
- Quadro de controle: tipo, versão, status, origem e data.
- Caixa de revisão humana quando houver IA.
- Títulos com hierarquia clara.
- Callouts para alertas, riscos e observações.
- Rodapé de confidencialidade e responsabilidade técnica.

## Implementado neste ciclo

- Estilos `.visual-law-*` em `frontend/src/styles/site-system.css`.
- Impressão de peças com aparência Visual Law usando `.print-view`.
- DOCX exportado com quadro inicial de controle Visual Law.

## Evolução recomendada

1. Criar componente React `VisualLawDocument` em PR separado, após estabilizar o design system base.
2. Criar templates Visual Law por tipo de documento: petição, contrato, parecer, notificação e relatório.
3. Aplicar Visual Law em dossiês de cliente, relatórios de IA e demonstrativos.
4. Permitir escolha de modelo: clássico jurídico, Visual Law e executivo.
