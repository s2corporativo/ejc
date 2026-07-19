// Guia Intuitivo do Sistema — conteúdo do manual navegável da Central de Ajuda.
//
// FONTE DE VERDADE: frontend/src/config/moduleRegistry.tsx. Cada ferramenta
// aqui aponta para uma rota REAL do EJC. Rotas contextuais (que abrem dentro
// de um caso/cliente específico) usam o padrão dinâmico do registry
// (ex.: "/casos/:id/jornada"); a Ajuda resolve o ponto de entrada navegável
// (a base, ex.: "/casos") e sinaliza que a ferramenta abre em contexto.
//
// A ordem dos grupos acompanha a jornada de trabalho do advogado:
// do cadastro do cliente à gestão contínua do caso, passando por produção,
// inteligência, prazos, financeiro e, por fim, administração.

export type PerfilGuia = "todos" | "advogado" | "gestor" | "cliente";

export interface FerramentaGuia {
  /** Identificador estável (usado como key e para busca/âncora). */
  id: string;
  /** Nome da ferramenta como aparece no menu/rota. */
  titulo: string;
  /** Rota real do moduleRegistry. Dinâmica (com ":") = abre em contexto. */
  rota: string;
  /** Uma frase: o que é a ferramenta. */
  oQueE: string;
  /** 1-2 frases: o problema do escritório que ela resolve. */
  paraQueServe: string;
  /** Passos numerados, em linguagem simples. */
  comoUsar: string[];
  /** Dica opcional de uso avançado ou boa prática. */
  dica?: string;
  /** Para quem a ferramenta é mais relevante. */
  perfil: PerfilGuia;
  /** Selo curto opcional (ex.: "Novo", "IA", "Beta"). */
  badge?: string;
}

export interface GrupoGuia {
  id: string;
  titulo: string;
  /** Uma frase explicando o momento da jornada que o grupo cobre. */
  descricao: string;
  ferramentas: FerramentaGuia[];
}

export const GUIA_SISTEMA: GrupoGuia[] = [
  {
    id: "inicio",
    titulo: "Primeiros passos",
    descricao: "Onde você começa o dia e tem a visão geral do escritório.",
    ferramentas: [
      {
        id: "dashboard",
        titulo: "Dashboard",
        rota: "/",
        oQueE: "A tela inicial com a visão executiva da operação jurídica.",
        paraQueServe:
          "Concentra os números do escritório e os atalhos do dia — prazos próximos, casos ativos, pendências e blocos administrativos — para você saber por onde começar sem procurar.",
        comoUsar: [
          "Ao entrar no sistema você já cai no Dashboard (menu Dashboard, no topo).",
          "Leia os cartões de indicadores no topo para o retrato imediato da operação.",
          "Use os atalhos rápidos para pular direto ao módulo que precisa (Novo Caso, Prazos, Financeiro...).",
        ],
        dica: "Vários módulos administrativos (Auditoria, Governança da IA, Produtividade) são alcançados pelos atalhos do Dashboard, mesmo estando fora do menu lateral.",
        perfil: "todos",
      },
    ],
  },
  {
    id: "clientes",
    titulo: "Clientes",
    descricao: "O cadastro de quem o escritório atende — a base de tudo.",
    ferramentas: [
      {
        id: "clientes",
        titulo: "Clientes",
        rota: "/clientes",
        oQueE: "O cadastro central de clientes e responsáveis do escritório.",
        paraQueServe:
          "Mantém em um só lugar os dados de contato, o tipo (pessoa física ou jurídica) e o histórico de cada cliente, evitando cadastros duplicados e informação espalhada em planilhas.",
        comoUsar: [
          "Abra Clientes no menu lateral.",
          "Busque por nome, CPF/CNPJ ou filtre pelo tipo de cliente.",
          "Clique em Novo Cliente e preencha contato, tipo (PF/PJ) e observações.",
          "Clique no cliente para abrir o Dossiê completo.",
        ],
        dica: "O sistema deduplica por CPF/CNPJ — se o cliente já existir, ele é reaproveitado ao abrir um novo caso.",
        perfil: "todos",
      },
      {
        id: "dossie-cliente",
        titulo: "Dossiê do Cliente",
        rota: "/clientes/:clientId",
        oQueE:
          "A página que reúne tudo de um cliente: casos, prazos, documentos, pendências e financeiro.",
        paraQueServe:
          "Dá a visão 360º do cliente em uma tela só, ideal para reuniões de acompanhamento e para saber, de relance, o que ainda falta o cliente entregar.",
        comoUsar: [
          "Em Clientes, clique no cliente desejado.",
          "Veja no topo os cartões de resumo: casos, prazos próximos, honorários e documentos.",
          "Use os botões de contato rápido (WhatsApp, ligar, e-mail) já apontados para os dados cadastrados.",
          "Acompanhe as Pendências e gere o relatório financeiro do cliente.",
        ],
        dica: "Revise as Pendências antes de protocolar — assim você cobra do cliente o que ainda falta em documentos, assinaturas ou pagamentos.",
        perfil: "todos",
      },
    ],
  },
  {
    id: "casos",
    titulo: "Casos e Processos",
    descricao:
      "O coração do sistema: da abertura do caso à estratégia e ao acompanhamento.",
    ferramentas: [
      {
        id: "caso-novo",
        titulo: "Novo Caso",
        rota: "/casos/novo",
        oQueE:
          "O assistente guiado que abre um caso ligando cliente e dados básicos em poucos passos.",
        paraQueServe:
          "Padroniza a entrada de casos para nada essencial ficar de fora e o cliente ser reaproveitado quando já existir, reduzindo retrabalho e cadastro inconsistente.",
        comoUsar: [
          "Clique em Novo Caso, em destaque no menu Principal.",
          "Informe o cliente — o sistema busca por CPF/CNPJ e reaproveita se já existir.",
          "Preencha os dados básicos do caso (área, parte contrária, tribunal, valor da causa).",
          "Conclua o assistente — o caso já nasce pronto para receber prazos, documentos e honorários.",
        ],
        dica: "Preencha a Prioridade (urgente/alta/média/baixa) já na abertura — ela aparece destacada na Sala de Guerra.",
        perfil: "advogado",
      },
      {
        id: "casos",
        titulo: "Casos e Processos",
        rota: "/casos",
        oQueE:
          "A gestão central de todos os casos e processos, em lista ou em quadro visual (Kanban).",
        paraQueServe:
          "Coloca todos os casos do escritório em um só lugar — judiciais, extrajudiciais e consultivos — com andamento visível, para nada se perder e a equipe enxergar o mesmo panorama.",
        comoUsar: [
          "Abra Casos e Processos no menu Principal.",
          "Alterne entre Lista (tabela) e Quadro (Kanban) no topo.",
          "No Quadro, arraste o cartão do caso entre as etapas para atualizar o andamento.",
          "Filtre por tipo (Judicial / Extrajudicial / Consultoria) e clique num caso para abrir o detalhe.",
        ],
        dica: "Ao soltar um caso na coluna Encerrado ou Acordo no Quadro, o status muda automaticamente.",
        perfil: "advogado",
      },
      {
        id: "caso-detalhe",
        titulo: "Detalhe do Caso",
        rota: "/casos/:id",
        oQueE:
          "O workspace de um caso específico, com abas de resumo, partes, documentos, prazos e ações.",
        paraQueServe:
          "Reúne tudo de um caso em um único ambiente de trabalho, para você não pular entre telas ao tocar um processo do início ao fim.",
        comoUsar: [
          "Em Casos e Processos, clique no caso desejado.",
          "Navegue pelas abas: Resumo, Timeline, Partes, Documentos, Checklists, Teses.",
          "Na aba Resumo, use as ações rápidas: Análise IA, Sincronizar DataJud, lançar horas, encerrar caso.",
          "Abra a Jornada ou a Sala de Guerra a partir dos botões do próprio caso.",
        ],
        dica: "Registre o campo Resultado ao encerrar o caso — ele alimenta os desfechos reais da Jurimetria.",
        perfil: "advogado",
      },
      {
        id: "caso-jornada",
        titulo: "Jornada do Caso",
        rota: "/casos/:id/jornada",
        oQueE:
          "A linha das 9 etapas do caso, do cliente à gestão contínua, com o que já foi feito e o que falta.",
        paraQueServe:
          "Mostra em que ponto o caso está e qual o próximo passo, guiando advogados e equipe de apoio por um fluxo padronizado sem depender de memória.",
        comoUsar: [
          "No detalhe de um caso, clique em Jornada do Caso.",
          "Percorra as etapas: Cliente, Triagem, Documentos, Inteligência, Estratégia, Produção, Revisão, Protocolo e Gestão.",
          "Veja as pendências de cada etapa e clique para abrir a ferramenta correspondente.",
          "Conclua as etapas na ordem para acompanhar o progresso do caso.",
        ],
        dica: "A etapa de Triagem leva direto à Entrevista Inteligente, com relato livre e apoio da IA.",
        perfil: "advogado",
        badge: "Jornada",
      },
      {
        id: "caso-entrevista",
        titulo: "Entrevista Inteligente",
        rota: "/casos/:id/entrevista",
        oQueE:
          "A triagem em texto livre onde você relata o ocorrido e a IA sugere uma análise preliminar.",
        paraQueServe:
          "Transforma o relato do cliente em uma triagem inicial estruturada, com nível de confiança por item, acelerando a definição da área e da estratégia do caso.",
        comoUsar: [
          "Na Jornada do Caso, abra a etapa Triagem (Entrevista Inteligente).",
          "Descreva os fatos em linguagem natural, como o cliente contou.",
          "Clique em Analisar e leia a triagem preliminar da IA.",
          "Confira o painel de confiança de cada item antes de aceitar as sugestões.",
        ],
        dica: "A IA é apoio analítico e nunca promete resultado — sempre revise antes de usar em peças ou orientações.",
        perfil: "advogado",
        badge: "IA",
      },
      {
        id: "sala-de-guerra",
        titulo: "Sala de Guerra",
        rota: "/casos/:caseId/sala-de-guerra",
        oQueE:
          "A visão estratégica consolidada de um caso complexo, com alertas, teses e horas da equipe.",
        paraQueServe:
          "Concentra o que importa para decidir a estratégia de um caso relevante — prazos críticos, pontos fortes/fracos e esforço da equipe — especialmente antes de audiências.",
        comoUsar: [
          "No detalhe de um caso, clique no botão Sala de Guerra.",
          "Confira o banner de alertas (prazos vencidos ou com menos de 7 dias).",
          "Clique em Editar para preencher Tese Principal, Pontos Fortes, Pontos Fracos e Observações.",
          "Acompanhe as horas por profissional e as teses vinculadas com taxa de sucesso histórica.",
        ],
        dica: "Preencha a análise estratégica antes de audiências — esses campos alimentam a Análise IA do caso.",
        perfil: "advogado",
      },
    ],
  },
  {
    id: "prazos-agenda",
    titulo: "Prazos e Agenda",
    descricao:
      "Tudo o que tem data: prazos, tarefas, intimações e compromissos, sem perder vencimento.",
    ferramentas: [
      {
        id: "atividades",
        titulo: "Central",
        rota: "/atividades",
        oQueE:
          "A tela única que reúne agenda, prazos, tarefas e intimações, mais o relacionamento com clientes.",
        paraQueServe:
          "Evita abrir várias telas para ver o dia: junta em um só lugar tudo o que tem data e o funil de relacionamento, com visões de lista, calendário e timeline.",
        comoUsar: [
          "Abra Central no menu Gestão.",
          "Escolha a forma de ver no topo: Lista (por urgência), Calendário (mês) ou Timeline (Vencidos → Hoje → 7 dias → Depois).",
          "Use os cartões coloridos para filtrar por urgência (vermelho = vencido, laranja = até 3 dias, amarelo = até 7 dias).",
          "Filtre por tipo (Prazo / Tarefa / Suspensão / Intimação) ou vá à aba de relacionamento.",
        ],
        dica: "Comece o dia pela aba Timeline — ela separa o que já venceu do que vence hoje e na semana.",
        perfil: "todos",
      },
      {
        id: "prazos",
        titulo: "Prazos",
        rota: "/prazos",
        oQueE:
          "O painel de controle de prazos processuais do escritório, ordenados por urgência.",
        paraQueServe:
          "Garante que nenhum prazo passe despercebido, com confirmação de cumprimento e destaque para os vencimentos mais próximos — o risco número um de qualquer escritório.",
        comoUsar: [
          "Abra Prazos no menu Gestão para ver todos os prazos ordenados por urgência.",
          "Adicione um prazo pela aba Prazos do caso: descrição, data, tipo e responsável.",
          "Marque como concluído ao cumprir — ele sai automaticamente dos alertas.",
          "Acompanhe os próximos 30 dias e os vencidos também pela Sala de Guerra.",
        ],
        dica: "Prazos urgentes (vencidos ou em até 7 dias) aparecem em banner vermelho na Sala de Guerra do caso.",
        perfil: "todos",
      },
      {
        id: "intimacoes",
        titulo: "Intimações",
        rota: "/intimacoes",
        oQueE:
          "A conferência das comunicações processuais recebidas, com apoio da IA na leitura.",
        paraQueServe:
          "Centraliza as intimações para que a equipe confira, classifique e transforme em prazos e tarefas, reduzindo o risco de uma comunicação importante escapar.",
        comoUsar: [
          "Abra Intimações no menu Gestão.",
          "Revise cada comunicação recebida e confira a leitura sugerida pela IA.",
          "Confirme, classifique e gere o prazo ou a tarefa correspondente.",
          "Marque como conferida para manter a caixa organizada.",
        ],
        dica: "Trate as intimações diariamente — cada uma pode esconder um prazo que começa a correr.",
        perfil: "advogado",
        badge: "IA",
      },
      {
        id: "tarefas",
        titulo: "Tarefas",
        rota: "/tarefas",
        oQueE: "A lista de tarefas operacionais atribuídas à equipe.",
        paraQueServe:
          "Organiza o que precisa ser feito e por quem, dando visibilidade da carga de trabalho e evitando combinações verbais que se perdem.",
        comoUsar: [
          "Acesse as tarefas pela Central (filtro Tipo = Tarefa) ou diretamente em Tarefas.",
          "Crie a tarefa com descrição, responsável e data.",
          "Acompanhe o andamento e marque como concluída.",
        ],
        dica: "A Central mostra as tarefas junto com prazos e intimações — use-a para o panorama do dia.",
        perfil: "todos",
      },
      {
        id: "suspensoes",
        titulo: "Suspensões",
        rota: "/suspensoes",
        oQueE:
          "O registro de suspensões processuais e seus reflexos sobre os prazos.",
        paraQueServe:
          "Controla períodos em que os prazos ficam suspensos (recessos, suspensões decretadas) para o cálculo de vencimentos não induzir a erro.",
        comoUsar: [
          "Acesse pela Central (filtro Tipo = Suspensão) ou diretamente em Suspensões.",
          "Registre o período de suspensão e o caso afetado.",
          "Confira como os prazos relacionados são recalculados.",
        ],
        perfil: "advogado",
      },
    ],
  },
  {
    id: "producao",
    titulo: "Produção Jurídica",
    descricao:
      "Onde os documentos e peças do escritório são criados, revisados e assinados.",
    ferramentas: [
      {
        id: "pecas",
        titulo: "Peças Jurídicas",
        rota: "/pecas",
        oQueE:
          "O ambiente de produção, validação, revisão e aprovação de peças, com apoio da IA e identidade Visual Law.",
        paraQueServe:
          "Acelera a redação de peças a partir de modelos e da IA, mantendo um fluxo claro de revisão e aprovação para nada sair sem conferência — com apresentação em Visual Law quando útil.",
        comoUsar: [
          "Abra Peças Jurídicas no menu Produção.",
          "Gere uma nova peça a partir de um modelo ou com apoio da IA.",
          "Revise o conteúdo — a IA é rascunho e exige conferência humana.",
          "Envie para aprovação e acompanhe o histórico de versões.",
        ],
        dica: "Os dados do caso alimentam as peças — mantenha o cadastro atualizado para minutas precisas.",
        perfil: "advogado",
        badge: "IA",
      },
      {
        id: "documentos",
        titulo: "Documentos e Data Room",
        rota: "/documentos",
        oQueE:
          "A gestão documental do escritório, incluindo o Data Room para compartilhamento controlado.",
        paraQueServe:
          "Guarda os documentos ligados a cada caso e cliente em um repositório seguro, com o Data Room para compartilhar arquivos com terceiros de forma controlada e rastreável.",
        comoUsar: [
          "Abra Documentos e Data Room no menu Produção.",
          "Visualize e baixe os documentos vinculados a cada caso.",
          "Gere minutas a partir do caso (procuração, contrato de honorários, relatório inicial).",
          "Use o Data Room para disponibilizar documentos a um cliente ou parte de forma controlada.",
        ],
        dica: "Filtre os documentos pelo caso (parâmetro ?caso= na URL, usado pela Jornada) para ver só o que interessa.",
        perfil: "todos",
      },
      {
        id: "assinaturas",
        titulo: "Assinaturas",
        rota: "/assinaturas",
        oQueE:
          "O fluxo de coleta de assinatura eletrônica com trilha e validade jurídica.",
        paraQueServe:
          "Permite colher assinaturas de documentos sem impressão, registrando identificação, data/hora, IP e hash (MP 2.200-2/2001) como comprovante.",
        comoUsar: [
          "Abra Assinaturas (também acessível pelos atalhos do Dashboard e pela paleta de comandos).",
          "Veja os documentos aguardando assinatura, separados dos já assinados.",
          "Clique em Assinar e confirme para registrar a trilha de autenticação.",
          "Guarde o hash exibido após a assinatura como comprovante.",
        ],
        dica: "O cliente também assina pelo Portal do Cliente, na aba de assinaturas.",
        perfil: "todos",
      },
      {
        id: "checklists",
        titulo: "Checklists",
        rota: "/checklists",
        oQueE:
          "Listas de verificação por área jurídica, vinculáveis à produção de cada caso.",
        paraQueServe:
          "Padroniza o passo a passo de cada tipo de trabalho para não esquecer etapas legais, com modelos prontos e referências de lei.",
        comoUsar: [
          "Abra Checklists ou vincule um pela aba Checklists do caso.",
          "Escolha o template da área (trabalhista, cível, empresarial, tributário...).",
          "Marque cada item ao concluir — a barra de progresso atualiza sozinha.",
          "Acompanhe o progresso na Sala de Guerra e no health score do caso.",
        ],
        dica: "Cada template traz 8-10 itens com referências legais — revise e adapte ao caso concreto.",
        perfil: "advogado",
        badge: "IA",
      },
      {
        id: "workflow",
        titulo: "Workflows",
        rota: "/workflow",
        oQueE: "A configuração de fluxos, etapas e SLAs por área jurídica.",
        paraQueServe:
          "Define como o trabalho anda em cada área (etapas e prazos internos), padronizando a operação e deixando claro o que vem depois de cada passo.",
        comoUsar: [
          "Abra Workflows (também pelos atalhos do Dashboard).",
          "Escolha ou crie um fluxo por área jurídica.",
          "Configure as etapas e os SLAs de cada uma.",
          "Aplique o fluxo aos casos para acompanhar o andamento padronizado.",
        ],
        perfil: "gestor",
      },
    ],
  },
  {
    id: "inteligencia",
    titulo: "Inteligência Jurídica",
    descricao:
      "A IA do escritório e a base de conhecimento que a torna precisa.",
    ferramentas: [
      {
        id: "inteligencia",
        titulo: "Inteligência Jurídica",
        rota: "/inteligencia",
        oQueE:
          "O workspace que reúne agentes de IA, análise, validação, jurimetria e conhecimento em abas.",
        paraQueServe:
          "Concentra as ferramentas de IA e análise em um só lugar — assistente, ferramentas, jurimetria e saúde da IA — para pesquisar, analisar e medir sem trocar de tela.",
        comoUsar: [
          "Abra Inteligência Jurídica no menu (visível para perfis jurídicos).",
          "Use a aba Assistente para perguntas em linguagem natural, com apoio da base de conhecimento.",
          "Explore a aba Jurimetria para taxa de sucesso, desfechos reais e desempenho por tribunal.",
          "Consulte as demais abas (ferramentas, conteúdo, saúde da IA) conforme a necessidade.",
        ],
        dica: "Registre o Resultado ao encerrar casos — a Jurimetria usa esses dados para os desfechos reais.",
        perfil: "advogado",
        badge: "IA",
      },
      {
        id: "knowledge-hub",
        titulo: "Conhecimento Jurídico",
        rota: "/knowledge-hub",
        oQueE:
          "A busca unificada em RAG, teses, jurisprudência e memória institucional.",
        paraQueServe:
          "Encontra em uma só busca o que o escritório já sabe — teses, precedentes, memória e documentos indexados — evitando reinventar a roda a cada novo caso.",
        comoUsar: [
          "Abra Conhecimento Jurídico no menu Inteligência.",
          "Digite o tema ou a pergunta na busca unificada.",
          "Percorra os resultados de RAG, teses, jurisprudência e memória.",
          "Abra um resultado para reaproveitar no caso em andamento.",
        ],
        dica: "Quanto mais documentos curados na base RAG, mais preciso fica o resultado da busca semântica.",
        perfil: "advogado",
        badge: "IA",
      },
      {
        id: "biblioteca",
        titulo: "Biblioteca Jurídica",
        rota: "/biblioteca",
        oQueE:
          "O acervo de teses, peças de referência e memória institucional do escritório.",
        paraQueServe:
          "Guarda as teses e peças de referência com sua taxa de sucesso, para a equipe reaproveitar argumentos que já funcionaram.",
        comoUsar: [
          "Abra Biblioteca Jurídica.",
          "Busque teses por área, tribunal, tipo ou palavra-chave.",
          "Use os filtros (área, tribunal, taxa de sucesso mínima) para refinar.",
          "Vincule a tese ao caso para acompanhar seu desempenho na Jurimetria.",
        ],
        perfil: "advogado",
      },
      {
        id: "memoria",
        titulo: "Memória Institucional",
        rota: "/memoria",
        oQueE:
          "O registro de resultados, aprendizados e precedentes internos do escritório.",
        paraQueServe:
          "Preserva o conhecimento de acordos vencedores, pareceres e estratégias consolidadas para que não se percam com a rotatividade da equipe.",
        comoUsar: [
          "Abra Memória Institucional.",
          "Registre acordos vencedores, pareceres e estratégias que deram certo.",
          "Categorize para facilitar a recuperação depois.",
          "Consulte a memória ao montar a estratégia de casos parecidos.",
        ],
        perfil: "advogado",
      },
      {
        id: "prompts",
        titulo: "Prompts Operacionais",
        rota: "/prompts",
        oQueE:
          "Os modelos de instrução reutilizáveis que padronizam o uso da IA pela equipe.",
        paraQueServe:
          "Guarda prompts prontos e testados para que todos obtenham respostas consistentes da IA, sem cada um reinventar a forma de pedir.",
        comoUsar: [
          "Abra Prompts Operacionais.",
          "Escolha um modelo de instrução existente ou crie um novo.",
          "Ajuste os campos variáveis ao seu caso.",
          "Reutilize o prompt no Assistente para respostas padronizadas.",
        ],
        perfil: "advogado",
        badge: "IA",
      },
      {
        id: "conhecimento-curadoria",
        titulo: "Curadoria RAG",
        rota: "/inteligencia?tab=conhecimento",
        oQueE:
          "A ingestão e curadoria da base de conhecimento vetorial que alimenta a IA.",
        paraQueServe:
          "Controla o que entra na base que a IA consulta — leis, súmulas, pareceres, PDFs e páginas — garantindo respostas mais precisas e confiáveis.",
        comoUsar: [
          "Abra Curadoria RAG (acesso restrito a gestores).",
          "Ingira conteúdo por texto (cole a lei/súmula/parecer com título e categoria).",
          "Ingira por PDF (o sistema extrai o texto e indexa) ou por URL de página pública.",
          "Categorize bem cada item (legislação, súmula, jurisprudência, doutrina) para facilitar a busca.",
        ],
        dica: "A curadoria é a fonte da precisão da IA — quanto melhor a base, melhores as respostas do Assistente e do Conhecimento Jurídico.",
        perfil: "gestor",
        badge: "IA",
      },
    ],
  },
  {
    id: "monitoramento",
    titulo: "Monitoramento e Dados Públicos",
    descricao:
      "As integrações que trazem informação oficial de fora para dentro do EJC.",
    ferramentas: [
      {
        id: "datajud",
        titulo: "Consulta DataJud",
        rota: "/datajud",
        oQueE:
          "A consulta e sincronização de dados processuais da base pública do CNJ (DataJud).",
        paraQueServe:
          "Traz dados oficiais de processos do Conselho Nacional de Justiça e sincroniza os andamentos no caso, poupando a conferência manual em cada tribunal.",
        comoUsar: [
          "Abra Consulta DataJud (também pelos atalhos do Dashboard e de dentro do caso).",
          "Digite o número do processo no padrão CNJ e busque.",
          "No detalhe de um caso com número de processo, use Sincronizar DataJud para trazer os andamentos.",
        ],
        dica: "Use o número completo (0000000-00.0000.0.00.0000) para resultados precisos.",
        perfil: "advogado",
        badge: "Integração",
      },
      {
        id: "diario-oficial",
        titulo: "Diário Oficial",
        rota: "/diario-oficial",
        oQueE:
          "O monitoramento de publicações por palavras-chave, com alertas.",
        paraQueServe:
          "Vigia as publicações oficiais pelas palavras-chave do escritório (nomes, OABs, processos) para você não descobrir uma publicação importante tarde demais.",
        comoUsar: [
          "Abra Diário Oficial (também pelo Radar Regulatório e atalhos do Dashboard).",
          "Cadastre as palavras-chave a monitorar.",
          "Acompanhe as publicações encontradas e os alertas gerados.",
        ],
        perfil: "advogado",
        badge: "Integração",
      },
      {
        id: "radar-regulatorio",
        titulo: "Radar Regulatório",
        rota: "/radar-regulatorio",
        oQueE:
          "A visão executiva dos alertas normativos relevantes para o escritório.",
        paraQueServe:
          "Resume as novidades regulatórias que podem afetar clientes e casos, para a equipe se antecipar a mudanças de norma.",
        comoUsar: [
          "Abra Radar Regulatório (atalho no Dashboard).",
          "Leia os alertas normativos priorizados.",
          "Aprofunde nos que impactam clientes ou casos ativos.",
        ],
        perfil: "advogado",
        badge: "Integração",
      },
      {
        id: "radar-compliance",
        titulo: "Radar de Compliance",
        rota: "/compliance/radar",
        oQueE: "A avaliação de riscos regulatórios e de conformidade.",
        paraQueServe:
          "Ajuda a mapear riscos de compliance e conformidade, apoiando pareceres e a orientação preventiva a clientes.",
        comoUsar: [
          "Abra Radar de Compliance (acesso para perfis de compliance).",
          "Analise os riscos regulatórios levantados.",
          "Use os achados para orientar clientes e montar planos de conformidade.",
        ],
        perfil: "advogado",
      },
      {
        id: "noticias",
        titulo: "Notícias Jurídicas",
        rota: "/noticias",
        oQueE: "As atualizações e o conteúdo jurídico externo agregados.",
        paraQueServe:
          "Reúne notícias e conteúdo jurídico relevante para a equipe se manter atualizada sem sair do sistema.",
        comoUsar: [
          "Veja o card de notícias no Dashboard para o uso diário.",
          "Abra Notícias Jurídicas para a lista completa.",
          "Leia e compartilhe o que for útil ao escritório.",
        ],
        perfil: "todos",
      },
    ],
  },
  {
    id: "ramos",
    titulo: "Áreas de Atuação",
    descricao:
      "Ferramentas, calculadoras e guias organizados por área de atuação.",
    ferramentas: [
      {
        id: "ramos",
        titulo: "Áreas de Atuação",
        rota: "/ramos",
        oQueE:
          "O hub das áreas jurídicas, cada uma com suas subáreas, guias e ferramentas oficiais.",
        paraQueServe:
          "Organiza por área (trabalhista, bancário, ambiental, tributário, previdenciário...) as subáreas atendidas, os links oficiais e as calculadoras, para orientar o atendimento e agilizar cálculos.",
        comoUsar: [
          "Abra Áreas de Atuação no menu Inteligência Jurídica.",
          "Clique na área desejada para ver as subáreas de atuação.",
          "Use os links de ferramentas públicas oficiais (PJe-Calc, Registrato/BACEN, Meu INSS, e-CAC, Consumidor.gov...).",
          "Aproveite as calculadoras embutidas de cada ramo (juros, prazos, liquidação...).",
        ],
        dica: "As ferramentas públicas e os índices do BCB e a consulta via Infosimples abrem por dentro dos ramos — são fontes oficiais de governo e tribunais.",
        perfil: "advogado",
        badge: "IA",
      },
      {
        id: "ramo-detalhe",
        titulo: "Núcleo Jurídico do Ramo",
        rota: "/ramos/:slug",
        oQueE:
          "A página especializada de um ramo, com seus guias e ferramentas específicas.",
        paraQueServe:
          "Concentra tudo de uma área — guia prático, calculadoras e integrações (como índices BCB e consultas Infosimples) — no contexto certo para quem atua naquele ramo.",
        comoUsar: [
          "Em Áreas de Atuação, clique na área desejada.",
          "Leia o guia da área e as subáreas atendidas.",
          "Preencha as calculadoras específicas e clique em calcular.",
          "Use as integrações do ramo (consultas oficiais, índices) quando disponíveis.",
        ],
        perfil: "advogado",
      },
    ],
  },
  {
    id: "financeiro",
    titulo: "Financeiro",
    descricao:
      "O caixa do escritório: honorários, despesas, contratos e gestão societária.",
    ferramentas: [
      {
        id: "financeiro",
        titulo: "Financeiro e Sociedade",
        rota: "/financeiro",
        oQueE:
          "A tela única de honorários, despesas, contratos e gestão societária do escritório.",
        paraQueServe:
          "Dá o retrato da saúde financeira em um lugar — caixa, a receber, a pagar e resultado do mês — e ainda organiza honorários, rateio de êxito e a vida societária (sócios, lucros e saques).",
        comoUsar: [
          "Abra Financeiro e Sociedade no menu (perfis financeiros e gestores).",
          "Leia os cartões do topo: caixa do período, a receber, a pagar e resultado do mês.",
          "Navegue pelas abas: honorários, despesas, recorrentes, contratos e societária.",
          "Troque o mês no seletor e gere o relatório gerencial quando precisar.",
        ],
        dica: "Cadastre despesas e honorários na competência (mês) certa — é o que liga cada lançamento ao período no Financeiro.",
        perfil: "gestor",
      },
    ],
  },
  {
    id: "atendimento",
    titulo: "Atendimento e Relacionamento",
    descricao: "Canais para captar leads e conversar com clientes.",
    ferramentas: [
      {
        id: "crm",
        titulo: "Funil de Leads",
        rota: "/crm-leads",
        oQueE:
          "O funil de captação, qualificação e conversão de leads em clientes.",
        paraQueServe:
          "Acompanha os interessados desde o primeiro contato até virarem clientes, para nenhuma oportunidade esfriar por falta de acompanhamento.",
        comoUsar: [
          "Acesse o funil pela Central (aba de relacionamento) ou por Funil de Leads.",
          "Cadastre o lead e mova-o pelas etapas de qualificação.",
          "Registre os contatos e o histórico de cada oportunidade.",
          "Converta o lead em cliente e abra o caso quando fechar.",
        ],
        perfil: "gestor",
      },
    ],
  },
  {
    id: "administracao",
    titulo: "Administração",
    descricao:
      "Governança, acessos, auditoria e ajustes — a parte de bastidores do sistema.",
    ferramentas: [
      {
        id: "configuracoes",
        titulo: "Preferências",
        rota: "/configuracoes",
        oQueE:
          "As preferências pessoais: aparência, navegação, segurança e conta.",
        paraQueServe:
          "Deixa cada usuário ajustar o sistema ao seu gosto — tema claro/escuro, navegação e segurança da conta (senha, 2FA).",
        comoUsar: [
          "Abra Preferências no menu Administração.",
          "Ajuste aparência (tema) e opções de navegação.",
          "Configure a segurança da conta (troca de senha, autenticação em duas etapas).",
        ],
        perfil: "todos",
      },
      {
        id: "administracao-configuracoes",
        titulo: "Administração do EJC",
        rota: "/configuracoes?tab=administracao",
        oQueE:
          "O painel de governança institucional e acesso aos painéis administrativos.",
        paraQueServe:
          "Reúne as configurações institucionais e os acessos administrativos para quem gere o escritório no sistema.",
        comoUsar: [
          "Abra Administração do EJC (perfis administradores).",
          "Ajuste as configurações institucionais.",
          "Acesse os painéis administrativos a partir daqui.",
        ],
        perfil: "gestor",
      },
      {
        id: "usuarios",
        titulo: "Usuários e Acessos",
        rota: "/usuarios",
        oQueE: "O cadastro da equipe, com status e perfis de acesso.",
        paraQueServe:
          "Controla quem entra no sistema e o que cada um pode ver ou fazer, respeitando a divisão de responsabilidades do escritório.",
        comoUsar: [
          "Abra Usuários e Acessos (perfis administradores).",
          "Cadastre um novo membro da equipe com o perfil adequado.",
          "Ative, desative ou ajuste o perfil de acesso conforme a função.",
        ],
        dica: "O perfil define o que a pessoa acessa — conceda o mínimo necessário para cada função.",
        perfil: "gestor",
      },
      {
        id: "governanca-ia",
        titulo: "Governança da IA",
        rota: "/ia-governanca",
        oQueE:
          "A governança da IA: curadoria, fontes, prompts sistêmicos e guardrails.",
        paraQueServe:
          "Define os limites e as fontes da IA do escritório, garantindo uso responsável e alinhado às políticas internas.",
        comoUsar: [
          "Abra Governança da IA (gestores; atalho no bloco administrativo do Dashboard).",
          "Revise as fontes e a curadoria que a IA utiliza.",
          "Ajuste os prompts sistêmicos e os guardrails de uso.",
        ],
        perfil: "gestor",
        badge: "IA",
      },
      {
        id: "auditoria",
        titulo: "Auditoria",
        rota: "/auditoria",
        oQueE:
          "A trilha imutável de todas as ações críticas realizadas no sistema.",
        paraQueServe:
          "Registra cada ação (login, criação, edição, exclusão, download) com usuário, data e IP — logs imutáveis exigidos pela LGPD (art. 37) e essenciais para rastrear qualquer evento.",
        comoUsar: [
          "Abra Auditoria (gestores; atalho no Dashboard).",
          "Filtre por tipo de ação e por módulo para achar um evento específico.",
          "Consulte o autor, a data e o IP de cada registro.",
        ],
        dica: "Antes de excluir algo importante, lembre: dá para restaurar na Lixeira, mas a exclusão fica registrada aqui.",
        perfil: "gestor",
      },
      {
        id: "lixeira",
        titulo: "Lixeira",
        rota: "/lixeira",
        oQueE:
          "O espaço de restauração e descarte controlado de itens excluídos.",
        paraQueServe:
          "Permite recuperar clientes, casos, prazos ou documentos apagados por engano, evitando perda de dados definitiva.",
        comoUsar: [
          "Abra Lixeira (gestores; atalho no Dashboard).",
          "Localize o item excluído que deseja recuperar.",
          "Restaure o item ou descarte-o em definitivo.",
        ],
        perfil: "gestor",
      },
      {
        id: "produtividade",
        titulo: "Produtividade",
        rota: "/produtividade",
        oQueE:
          "Os indicadores operacionais da equipe: horas por advogado e por área.",
        paraQueServe:
          "Mostra quanto e onde a equipe trabalha, separando horas faturáveis do total, para apoiar decisões de gestão e precificação.",
        comoUsar: [
          "Abra Produtividade (gestores; atalho no bloco administrativo do Dashboard).",
          "Escolha o período no seletor (7 dias, 30 dias, 3 meses, 1 ano).",
          "Compare horas por advogado (com % faturável) e a distribuição por área.",
          "Acompanhe a tendência de horas ao longo do período.",
        ],
        dica: "Os números dependem do lançamento de horas por caso — incentive a equipe a lançar diariamente.",
        perfil: "gestor",
      },
      {
        id: "mapa-modulos",
        titulo: "Mapa de Módulos",
        rota: "/mapa-modulos",
        oQueE: "O inventário técnico e funcional de todos os módulos do EJC.",
        paraQueServe:
          "Dá uma visão de conjunto do que existe no sistema e como se relaciona, útil para gestão e para entender a cobertura funcional.",
        comoUsar: [
          "Abra Mapa de Módulos (gestores; atalho no Dashboard).",
          "Navegue pelo inventário de módulos e suas funções.",
          "Use como referência para entender a cobertura do sistema.",
        ],
        perfil: "gestor",
        badge: "Beta",
      },
    ],
  },
];

/** Total de ferramentas cobertas pelo guia (para exibição/relatório). */
export const TOTAL_FERRAMENTAS = GUIA_SISTEMA.reduce(
  (soma, grupo) => soma + grupo.ferramentas.length,
  0,
);

/** Rótulo curto de cada perfil, para exibir nos cards. */
export const PERFIL_LABEL: Record<PerfilGuia, string> = {
  todos: "Todos",
  advogado: "Advogado",
  gestor: "Gestor",
  cliente: "Cliente",
};
