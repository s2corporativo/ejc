import { useState, useMemo } from "react";
import { Search, ChevronRight, Lightbulb, ArrowLeft } from "lucide-react";

interface Step {
  title: string;
  desc: string;
}
interface Module {
  id: string;
  icon: string;
  title: string;
  sub: string;
  steps: Step[];
  tip?: string;
  badge?: string;
  section: string;
}

const MODULES: Module[] = [
  {
    id: "casos",
    icon: "⚖️",
    title: "Casos",
    sub: "Criar e acompanhar processos",
    section: "Gestão de Casos",
    steps: [
      { title: "Acessar", desc: "Clique em Casos no menu lateral esquerdo." },
      {
        title: "Novo caso",
        desc: "Botão + Novo Caso. Preencha área, parte contrária, tribunal e valor da causa.",
      },
      {
        title: "Detalhes",
        desc: "Clique no nome do caso para abrir abas: Resumo, Timeline, Partes, Documentos, Checklists, Teses.",
      },
      {
        title: "Ações rápidas",
        desc: "Na aba Resumo: Análise IA, Sincronizar DataJud, Encerrar caso, Sala de Guerra.",
      },
    ],
    tip: "Use o campo Prioridade (urgente/alta/média/baixa) — ele aparece destacado na Sala de Guerra.",
  },
  {
    id: "sala",
    icon: "⚔️",
    title: "Sala de Guerra",
    sub: "Visão consolidada para casos complexos",
    section: "Gestão de Casos",
    badge: "Novo",
    steps: [
      {
        title: "Acessar",
        desc: "No detalhe de um caso, clique no botão ⚔️ Sala de Guerra.",
      },
      {
        title: "Alertas",
        desc: "Prazos vencidos ou com menos de 7 dias aparecem em banner vermelho no topo automaticamente.",
      },
      {
        title: "Análise estratégica",
        desc: "Clique em Editar para preencher Tese Principal, Pontos Fortes, Pontos Fracos e Observações.",
      },
      {
        title: "Horas & time",
        desc: "HH total por profissional com breakdown faturável/não-faturável e número de casos.",
      },
      {
        title: "Teses vinculadas",
        desc: "Mostra as teses da Biblioteca já vinculadas ao caso com taxa de sucesso histórica.",
      },
    ],
    tip: "Preencha Tese Principal e Pontos Fortes/Fracos antes de audiências — esses campos alimentam a análise IA.",
  },
  {
    id: "prazos",
    icon: "📅",
    title: "Prazos",
    sub: "Controle de vencimentos e alertas",
    section: "Gestão de Casos",
    steps: [
      {
        title: "Painel geral",
        desc: "Menu Prazos — todos os prazos do escritório ordenados por urgência.",
      },
      {
        title: "Adicionar",
        desc: "Na aba Prazos do caso, clique + Adicionar. Informe descrição, data, tipo e responsável.",
      },
      {
        title: "Concluir",
        desc: "Marque como concluído — sai automaticamente dos alertas.",
      },
      {
        title: "Sala de Guerra",
        desc: "Mostra os próximos 30 dias + todos os vencidos não concluídos.",
      },
    ],
    tip: "Prazos urgentes (vencidos ou ≤7 dias) aparecem em banner vermelho na Sala de Guerra.",
  },
  {
    id: "checklists",
    icon: "✅",
    title: "Checklists",
    sub: "Fluxos de trabalho por área jurídica",
    section: "Gestão de Casos",
    steps: [
      {
        title: "Templates",
        desc: "8 templates prontos: trabalhista, cível, empresarial, administrativo, tributário, penal, ambiental, bancário.",
      },
      {
        title: "Vincular",
        desc: "Na aba Checklists do caso, clique + Checklist e escolha o template.",
      },
      {
        title: "Marcar itens",
        desc: "Clique em cada item para concluir. O progresso atualiza automaticamente.",
      },
      {
        title: "Acompanhar",
        desc: "A barra de progresso aparece na Sala de Guerra e no Health Score do caso.",
      },
    ],
    tip: "Cada template tem 8-10 itens com referências legais (artigos de lei) — revise e adapte ao caso.",
  },
  {
    id: "clientes",
    icon: "👥",
    title: "Clientes",
    sub: "CRM e dossiê completo",
    section: "Clientes & Financeiro",
    steps: [
      {
        title: "Listar",
        desc: "Menu Clientes — busque por nome, CPF/CNPJ ou filtre por tipo.",
      },
      {
        title: "Novo cliente",
        desc: "Botão + Novo Cliente. Preencha contato, tipo (PF/PJ) e observações.",
      },
      {
        title: "Dossiê",
        desc: "No card do cliente, clique 📋 para o Dossiê: resumo financeiro, casos, prazos, documentos.",
      },
      {
        title: "Conflito",
        desc: "O sistema verifica conflito de interesses automaticamente ao cadastrar novos casos.",
      },
    ],
    tip: "O Dossiê mostra honorários totais/recebidos/pendentes por cliente — útil para reuniões de acompanhamento.",
  },
  {
    id: "honorarios",
    icon: "💰",
    title: "Honorários",
    sub: "Faturamento e controle financeiro",
    section: "Clientes & Financeiro",
    steps: [
      {
        title: "Registrar",
        desc: "No caso, botão 💰 Honorários (OAB) ou menu lateral Honorários.",
      },
      {
        title: "Sugestão IA",
        desc: "Clique Sugerir Honorários — a IA consulta a Tabela OAB/MG pela área e valor da causa.",
      },
      {
        title: "Pagamentos",
        desc: "Registre cada parcela como pendente, recebida ou cancelada.",
      },
      {
        title: "Relatório",
        desc: "O dashboard financeiro mostra inadimplência, recebimentos do mês e projeção.",
      },
    ],
    tip: "Use o campo Faturável ao lançar horas — o Dashboard de Produtividade separa HH faturável do total.",
  },
  {
    id: "horas",
    icon: "⏱️",
    title: "Lançamento de Horas",
    sub: "Timesheet por caso",
    section: "Clientes & Financeiro",
    steps: [
      {
        title: "Lançar",
        desc: "Na aba Resumo do caso, clique + Lançar horas. Informe data, minutos, descrição e se é faturável.",
      },
      {
        title: "Sala de Guerra",
        desc: "Mostra HH por profissional com breakdown faturável/não-faturável.",
      },
      {
        title: "Dashboard",
        desc: "Menu Produtividade — HH por advogado e por área com seletor de período (7d/30d/90d/1ano).",
      },
    ],
    tip: "Lance horas logo após cada atividade — o relatório mensal de produtividade depende desses dados.",
  },
  {
    id: "ia",
    icon: "✨",
    title: "Análise com IA",
    sub: "Assistente jurídico integrado",
    section: "Inteligência & IA",
    steps: [
      {
        title: "Análise de caso",
        desc: "No detalhe do caso, clique Análise IA. A IA analisa fatos, área e sugere estratégia.",
      },
      {
        title: "Contratos",
        desc: "Na aba Ferramentas do caso, use Análise de Contrato IA — identifica cláusulas de risco.",
      },
      {
        title: "Honorários",
        desc: "Botão Sugerir Honorários consulta Tabela OAB/MG com base na área e valor.",
      },
      {
        title: "Assistente geral",
        desc: "Menu Assistente IA — chat livre para consultas jurídicas, pesquisa e rascunhos.",
      },
      {
        title: "Base RAG",
        desc: "O Assistente busca automaticamente na base do escritório (teses, memória institucional).",
      },
    ],
    tip: "A IA nunca promete resultados — as respostas são analíticas. Revise sempre antes de usar em peças.",
  },
  {
    id: "biblioteca",
    icon: "📚",
    title: "Biblioteca & RAG",
    sub: "Teses jurídicas e base de conhecimento",
    section: "Inteligência & IA",
    badge: "Novo",
    steps: [
      {
        title: "Teses jurídicas",
        desc: "Menu Biblioteca — busque teses por área, tribunal, tipo ou palavra-chave.",
      },
      {
        title: "Busca avançada",
        desc: "Filtros: área do direito, tribunal, taxa de sucesso mínima. Busca semântica em texto completo.",
      },
      {
        title: "Upload PDF",
        desc: "Menu Base RAG, botão Upload PDF — envie acórdãos, doutrinas ou peças para indexar.",
      },
      {
        title: "Ingerir URL",
        desc: "Botão Ingerir por URL — cole link de notícia ou artigo jurídico para indexar automaticamente.",
      },
      {
        title: "Memória Institucional",
        desc: "Menu Memória Institucional — registre acordos vencedores, pareceres e estratégias consolidadas.",
      },
    ],
    tip: "Quanto mais documentos indexados, mais precisa fica a busca semântica do Assistente IA.",
  },
  {
    id: "jurimetria",
    icon: "📊",
    title: "Jurimetria",
    sub: "Análise estatística de desempenho",
    section: "Inteligência & IA",
    badge: "Aprimorado",
    steps: [
      { title: "Acessar", desc: "Menu Jurimetria em Inteligência." },
      {
        title: "Visão geral",
        desc: "Taxa de sucesso geral, vínculos tese↔caso, teses ativas e casos analisados.",
      },
      {
        title: "Por tribunal",
        desc: "Identifique em quais tribunais o escritório tem mais sucesso histórico.",
      },
      {
        title: "Desfechos reais",
        desc: "Novo: mostra resultados reais dos casos encerrados (campo Resultado), não apenas vínculos de teses.",
      },
    ],
    tip: "Registre sempre o campo Resultado ao encerrar um caso — alimenta os Desfechos Reais na Jurimetria.",
  },
  {
    id: "produtividade",
    icon: "📈",
    title: "Produtividade",
    sub: "HH por advogado e por área",
    section: "Inteligência & IA",
    badge: "Novo",
    steps: [
      { title: "Acessar", desc: "Menu Produtividade em Inteligência." },
      {
        title: "Período",
        desc: "Seletor no topo: 7 dias, 30 dias, 3 meses, 1 ano.",
      },
      {
        title: "Por advogado",
        desc: "Barras comparativas com total de horas, % faturável e casos atendidos.",
      },
      {
        title: "Por área",
        desc: "Distribuição das horas entre as áreas jurídicas do escritório.",
      },
      {
        title: "Tendência",
        desc: "Mini-gráfico de barras mostrando a evolução de HH dia a dia no período selecionado.",
      },
    ],
    tip: "Dados dependem do lançamento de horas por caso. Incentive a equipe a lançar diariamente.",
  },
  {
    id: "documentos",
    icon: "📄",
    title: "Documentos & Peças",
    sub: "Gestão documental e minutas",
    section: "Documentos",
    steps: [
      {
        title: "Documentos",
        desc: "Menu Documentos — visualize e baixe documentos vinculados a cada caso.",
      },
      {
        title: "Gerar minutas",
        desc: "No caso, botão 📄 Gerar documentos — cria Procuração, Contrato de Honorários e Relatório Inicial.",
      },
      {
        title: "Peças jurídicas",
        desc: "Menu Peças — histórico de peças geradas com IA, revisão e aprovação.",
      },
      {
        title: "Data Room",
        desc: "Menu Data Room — repositório seguro de documentos por cliente.",
      },
    ],
    tip: "As minutas geradas usam os dados do cadastro do caso — mantenha os dados atualizados para minutas precisas.",
  },
  {
    id: "casos-processos",
    icon: "📁",
    title: "Casos e Processos (Kanban e Fluxos)",
    sub: "Para que serve: organizar todos os casos do escritório em um só lugar, em lista ou em quadro visual",
    section: "Gestão de Casos",
    badge: "Novo",
    steps: [
      {
        title: "O que é",
        desc: "É o coração do sistema. Todo caso aberto em qualquer área aparece aqui automaticamente — judicial, extrajudicial ou consultoria.",
      },
      {
        title: "Ver em Lista ou Quadro",
        desc: "No topo, alterne entre Lista (tabela) e Quadro (Kanban com colunas). O Quadro mostra o andamento arrastando o caso entre etapas.",
      },
      {
        title: "Tipo de caso",
        desc: "Ao criar, escolha o tipo: Judicial, Extrajudicial (notificação, acordo, contrato...) ou Consultoria. Cada tipo tem seu próprio fluxo de colunas no Quadro.",
      },
      {
        title: "Mover no Quadro",
        desc: "Arraste o cartão do caso para a próxima coluna. Ao soltar em 'Encerrado' ou 'Acordo', o status do caso muda sozinho.",
      },
      {
        title: "Virar processo judicial",
        desc: "Num caso extrajudicial, abra o detalhe e clique em 'Converter em processo judicial' — cria um caso judicial ligado ao original.",
      },
    ],
    tip: "Filtre por tipo (Judicial/Extrajudicial/Consultoria) usando os botões acima da lista.",
  },
  {
    id: "agenda-prazos",
    icon: "📆",
    title: "Agenda & Prazos (tela única)",
    sub: "Para que serve: ver prazos, tarefas, suspensões, intimações e compromissos juntos, numa só tela",
    section: "Gestão de Casos",
    badge: "Novo",
    steps: [
      {
        title: "O que é",
        desc: "Reúne tudo o que tem data: prazos processuais, tarefas, suspensões e intimações — sem precisar abrir telas separadas.",
      },
      {
        title: "3 formas de ver",
        desc: "No topo escolha: Lista (ordenada por urgência), Calendário (mês) ou Timeline (linha do tempo: Vencidos → Hoje → 7 dias → Depois).",
      },
      {
        title: "Cores de urgência",
        desc: "Vermelho = vencido, laranja = até 3 dias, amarelo = até 7 dias. Os cartões coloridos no topo filtram por urgência ao clicar.",
      },
      {
        title: "Filtrar por tipo",
        desc: "Botões Prazo / Tarefa / Suspensão / Intimação mostram só aquele tipo.",
      },
    ],
    tip: "Comece o dia pela aba Timeline — ela separa o que está vencido do que vence hoje e na semana.",
  },
  {
    id: "dossie",
    icon: "🗂️",
    title: "Dossiê do Cliente",
    sub: "Para que serve: ver tudo de um cliente numa página — casos, prazos, documentos, pendências e financeiro",
    section: "Clientes & Financeiro",
    steps: [
      {
        title: "Abrir",
        desc: "Em Clientes, clique no cliente e depois em 'Dossiê' (ou no ícone de pasta).",
      },
      {
        title: "Resumo no topo",
        desc: "Cartões mostram total de casos, prazos próximos, honorários e documentos.",
      },
      {
        title: "Contato rápido",
        desc: "Botões de WhatsApp, Ligar e E-mail abrem direto no número/e-mail cadastrado do cliente.",
      },
      {
        title: "Pendências",
        desc: "Liste o que falta o cliente entregar (documentos, assinaturas, pagamentos) e acompanhe o status de cada item.",
      },
      {
        title: "Relatório financeiro",
        desc: "Clique em 'Gerar relatório' para ver contratos, honorários pagos/pendentes, êxito e despesas — com exportação em CSV/PDF.",
      },
    ],
    tip: "Use as Pendências antes de protocolar — assim você cobra do cliente o que ainda falta.",
  },
  {
    id: "whatsapp",
    icon: "💬",
    title: "WhatsApp",
    sub: "Para que serve: conversar com clientes pelo WhatsApp dentro do sistema",
    section: "Atendimento",
    steps: [
      {
        title: "Conectar",
        desc: "Na primeira vez, a tela mostra um QR Code. Abra o WhatsApp do celular → Aparelhos conectados → Conectar aparelho → aponte para o QR.",
      },
      {
        title: "Conversas",
        desc: "Depois de conectado, suas conversas aparecem na lista à esquerda. Clique numa para abrir.",
      },
      {
        title: "Enviar mensagem",
        desc: "Digite no campo de baixo e tecle Enviar. As mensagens ficam registradas.",
      },
      {
        title: "Abrir pelo cliente",
        desc: "No Dossiê do Cliente, o botão WhatsApp já abre a conversa no número cadastrado.",
      },
    ],
    tip: "Se aparecer 'desconectado', refaça a leitura do QR Code — o celular precisa estar com internet.",
  },
  {
    id: "datajud",
    icon: "🔎",
    title: "Busca DataJud (CNJ)",
    sub: "Para que serve: consultar dados oficiais de processos na base pública do CNJ",
    section: "Atendimento",
    steps: [
      {
        title: "O que é",
        desc: "Consulta a base nacional de processos do Conselho Nacional de Justiça (CNJ).",
      },
      {
        title: "Buscar",
        desc: "Digite o número do processo (padrão CNJ) e clique em buscar.",
      },
      {
        title: "Sincronizar no caso",
        desc: "No detalhe de um caso com número de processo, use 'Sincronizar DataJud' para trazer os andamentos automaticamente.",
      },
    ],
    tip: "Use o número completo no formato 0000000-00.0000.0.00.0000 para resultados precisos.",
  },
  {
    id: "ramos",
    icon: "⚖️",
    title: "Ramos do Direito e Ferramentas",
    sub: "Para que serve: áreas especializadas com subáreas de atuação e ferramentas públicas oficiais",
    section: "Inteligência & IA",
    steps: [
      {
        title: "Escolher o ramo",
        desc: "Em Ramos do Direito, clique na área (Empresarial, Trabalhista, Bancário, Consumidor, Família, etc.).",
      },
      {
        title: "Áreas de atuação",
        desc: "Cada ramo lista as subáreas que o escritório atende — útil para orientar o atendimento.",
      },
      {
        title: "Ferramentas públicas",
        desc: "Links oficiais por área: PJe-Calc (trabalhista), Registrato/BACEN (bancário), MapBiomas (ambiental), PNCP (licitações), Meu INSS (previdenciário), Consumidor.gov, e-CAC (tributário).",
      },
      {
        title: "Calculadoras",
        desc: "Alguns ramos têm calculadoras embutidas (ex.: prazos de Recuperação Judicial, verificação CADE, análise de juros). Preencha os campos e clique em calcular.",
      },
    ],
    tip: "As ferramentas públicas abrem em nova aba — são sites oficiais do governo e tribunais.",
  },
  {
    id: "financeiro",
    icon: "💰",
    title: "Financeiro (tela única)",
    sub: "Para que serve: controlar caixa, receitas e despesas do escritório numa só tela",
    section: "Clientes & Financeiro",
    badge: "Novo",
    steps: [
      {
        title: "Cartões do topo",
        desc: "Caixa do período, A Receber, A Pagar e Resultado do mês — visão imediata da saúde financeira.",
      },
      {
        title: "Receitas classificadas",
        desc: "Separa Honorários Contratuais, Êxito (Ad Exitum), Sucumbência e Custas — para saber de onde vem o dinheiro.",
      },
      {
        title: "Despesas por categoria",
        desc: "Mostra custos fixos e variáveis por categoria (infraestrutura, marketing, fiscal...).",
      },
      {
        title: "Trocar o mês",
        desc: "Use o seletor de mês no topo para ver outro período. 'Relatório' abre o resumo gerencial.",
      },
    ],
    tip: "Cadastre as despesas com a competência (mês) certa — senão não aparecem no período.",
  },
  {
    id: "exito",
    icon: "🤝",
    title: "Rateio de Êxito 50/50",
    sub: "Para que serve: dividir automaticamente o honorário de êxito entre advogado titular e escritório",
    section: "Clientes & Financeiro",
    badge: "Novo",
    steps: [
      {
        title: "Regra",
        desc: "Após receber um honorário de êxito, o sistema calcula: valor bruto − despesas do caso = líquido. Desse líquido, 50% vai ao advogado titular e 50% ao escritório.",
      },
      {
        title: "Onde fazer",
        desc: "Em Honorários, num lançamento de tipo 'Êxito' já PAGO, clique no ícone de divisão (Split).",
      },
      {
        title: "Conferir",
        desc: "A tela mostra bruto, despesas, líquido e as duas metades. Confira antes de gerar.",
      },
      {
        title: "Gerar saque",
        desc: "Clique em 'Gerar saque do titular' — cria o saque do sócio (pendente de aprovação em Societária → Saques).",
      },
    ],
    tip: "O advogado titular precisa estar cadastrado como sócio para o saque ser gerado automaticamente.",
  },
  {
    id: "societaria",
    icon: "🏛️",
    title: "Societária (sócios, lucros e saques)",
    sub: "Para que serve: gerir os sócios, a participação de cada um, distribuição de lucros e saques",
    section: "Clientes & Financeiro",
    steps: [
      {
        title: "Sócios",
        desc: "Aba Sócios: cada sócio com sua participação (%), regime e papel (administrador, técnico, operacional).",
      },
      {
        title: "Distribuição de lucros",
        desc: "Aba Distribuição: registra o quanto cabe a cada sócio conforme a participação.",
      },
      {
        title: "Saques",
        desc: "Aba Saques: pedidos de retirada. Os saques de êxito gerados automaticamente aparecem aqui como 'pendente'.",
      },
      {
        title: "Aprovar",
        desc: "Sócio administrador aprova ou rejeita cada saque pendente.",
      },
    ],
    tip: "A soma das participações dos sócios ativos deve fechar em 100%.",
  },
  {
    id: "conhecimento",
    icon: "📚",
    title: "Base de Conhecimento (RAG)",
    sub: "Para que serve: alimentar a IA com seus documentos, leis e jurisprudência para respostas mais precisas",
    section: "Inteligência & IA",
    steps: [
      {
        title: "O que é",
        desc: "Uma biblioteca que a IA consulta. Quanto mais você ingere, melhores as respostas do Assistente.",
      },
      {
        title: "Ingerir por texto",
        desc: "Cole o texto (lei, súmula, parecer), dê um título e categoria, e salve.",
      },
      {
        title: "Ingerir PDF",
        desc: "Envie um arquivo PDF — o sistema extrai o texto automaticamente e indexa.",
      },
      {
        title: "Ingerir por link",
        desc: "Cole a URL de uma página pública — o sistema busca, limpa e indexa o conteúdo.",
      },
    ],
    tip: "Categorize bem (legislação, súmula, jurisprudência, doutrina) — facilita a busca depois.",
  },
  {
    id: "assistente",
    icon: "🤖",
    title: "Assistente IA",
    sub: "Para que serve: tirar dúvidas jurídicas e pesquisar usando a base de conhecimento do escritório",
    section: "Inteligência & IA",
    steps: [
      {
        title: "Perguntar",
        desc: "Digite sua pergunta em linguagem natural, como faria a um colega.",
      },
      {
        title: "Respostas com fonte",
        desc: "A IA responde usando os documentos que você ingeriu na Base de Conhecimento.",
      },
      {
        title: "Revisar sempre",
        desc: "A IA é um apoio analítico — nunca promete resultado. Confira antes de usar em peças.",
      },
    ],
    tip: "Se a resposta vier vaga, ingira mais documentos sobre o tema na Base de Conhecimento.",
  },
  {
    id: "assinaturas",
    icon: "✍️",
    title: "Assinaturas Eletrônicas",
    sub: "Para que serve: coletar assinatura eletrônica de documentos com validade jurídica",
    section: "Documentos",
    steps: [
      {
        title: "Documentos pendentes",
        desc: "A tela lista os documentos aguardando assinatura, separados dos já assinados.",
      },
      {
        title: "Assinar",
        desc: "Clique em Assinar e confirme — registra identificação, data/hora, IP e hash do arquivo (MP 2.200-2/2001).",
      },
      {
        title: "Comprovante",
        desc: "Após assinar, aparece o hash do documento como comprovante.",
      },
    ],
    tip: "O cliente também assina pelo Portal do Cliente, na aba Assinaturas.",
  },
  {
    id: "despesas",
    icon: "🧾",
    title: "Despesas do Escritório",
    sub: "Para que serve: registrar e categorizar os gastos fixos e variáveis do escritório",
    section: "Clientes & Financeiro",
    steps: [
      {
        title: "Lançar",
        desc: "Clique em nova despesa. Informe descrição, valor, categoria, tipo (fixo/variável) e competência (mês).",
      },
      {
        title: "Categorias",
        desc: "Infraestrutura, tecnologia, pessoal, OAB, marketing, operação, fiscal, investimento.",
      },
      {
        title: "Recorrentes",
        desc: "Despesas que se repetem todo mês (aluguel, internet) podem ser marcadas como recorrentes.",
      },
      {
        title: "Ver no Financeiro",
        desc: "Tudo aparece consolidado na tela Financeiro, por categoria e fixo/variável.",
      },
    ],
    tip: "Sempre preencha a competência (mês) — é o que liga a despesa ao período no Financeiro.",
  },
  {
    id: "portal",
    icon: "🌐",
    title: "Portal do Cliente",
    sub: "Para que serve: o ambiente onde o seu cliente acompanha os próprios casos",
    section: "Atendimento",
    steps: [
      {
        title: "O que o cliente vê",
        desc: "Painel com casos ativos, financeiro, mensagens e assinaturas — só os dados dele.",
      },
      {
        title: "Processos",
        desc: "O cliente acompanha o andamento dos próprios processos.",
      },
      {
        title: "Mensagens",
        desc: "Canal de mensagens por caso entre cliente e escritório.",
      },
      {
        title: "Acesso",
        desc: "O cliente entra com login próprio (perfil cliente externo) — não enxerga dados de outros clientes.",
      },
    ],
    tip: "Use as Mensagens do Portal para manter o histórico de comunicação organizado por caso.",
  },
  {
    id: "auditoria",
    icon: "🛡️",
    title: "Auditoria e Lixeira",
    sub: "Para que serve: rastrear tudo que foi feito no sistema e recuperar itens excluídos",
    section: "Documentos",
    steps: [
      {
        title: "Auditoria",
        desc: "Registra cada ação (login, criação, edição, exclusão, download) com usuário, data e IP — logs imutáveis (LGPD art. 37).",
      },
      {
        title: "Filtrar",
        desc: "Filtre por tipo de ação e por módulo para encontrar um evento específico.",
      },
      {
        title: "Lixeira",
        desc: "Itens excluídos (clientes, casos, prazos, documentos...) podem ser restaurados na Lixeira.",
      },
    ],
    tip: "Antes de excluir algo importante, lembre: dá para restaurar na Lixeira — mas a exclusão fica registrada na Auditoria.",
  },
];
const SECTIONS_ORDER = [
  "Gestão de Casos",
  "Atendimento",
  "Clientes & Financeiro",
  "Documentos",
  "Inteligência & IA",
];

export default function Ajuda() {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<Module | null>(null);

  const filtrados = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return MODULES;
    return MODULES.filter(
      (m) =>
        m.title.toLowerCase().includes(t) ||
        m.sub.toLowerCase().includes(t) ||
        m.steps.some(
          (s) =>
            s.title.toLowerCase().includes(t) ||
            s.desc.toLowerCase().includes(t),
        ),
    );
  }, [q]);

  const porSecao = useMemo(() => {
    const map: Record<string, Module[]> = {};
    for (const m of filtrados) (map[m.section] ??= []).push(m);
    const secoes = Object.keys(map).sort((a, b) => {
      const ia = SECTIONS_ORDER.indexOf(a),
        ib = SECTIONS_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
    return secoes.map((s) => ({ secao: s, itens: map[s] }));
  }, [filtrados]);

  // Detalhe de um tutorial
  if (sel) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-6">
        <button
          onClick={() => setSel(null)}
          className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-4"
        >
          <ArrowLeft size={15} /> Voltar
        </button>
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
          <div className="flex items-start gap-3 mb-5">
            <span className="text-3xl">{sel.icon}</span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-800">
                  {sel.title}
                </h1>
                {sel.badge && (
                  <span className="text-[10px] font-bold bg-success-100 text-success-700 px-2 py-0.5 rounded-full">
                    {sel.badge}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-500 mt-0.5">{sel.sub}</p>
            </div>
          </div>
          <ol className="space-y-3">
            {sel.steps.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-navy text-white text-sm font-bold flex items-center justify-center">
                  {i + 1}
                </span>
                <div>
                  <p className="font-medium text-slate-800 text-sm">
                    {s.title}
                  </p>
                  <p className="text-sm text-slate-600 mt-0.5">{s.desc}</p>
                </div>
              </li>
            ))}
          </ol>
          {sel.tip && (
            <div className="mt-5 flex items-start gap-2 bg-warn-50 border border-warn-200 rounded-xl px-4 py-3">
              <Lightbulb
                size={16}
                className="text-warn-600 flex-shrink-0 mt-0.5"
              />
              <p className="text-sm text-warn-800">{sel.tip}</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Lista de tutoriais
  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-slate-800">Central de Ajuda</h1>
        <p className="text-slate-500 text-sm mt-1">
          Tutoriais passo a passo de cada ferramenta — escolha um tema para
          aprender.
        </p>
      </div>
      <div className="relative max-w-md mb-6">
        <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
        <input
          className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
          placeholder="Buscar ferramenta ou assunto..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {porSecao.length === 0 ? (
        <p className="text-slate-400 text-sm text-center py-12">
          Nenhum tutorial encontrado para "{q}".
        </p>
      ) : (
        porSecao.map(({ secao, itens }) => (
          <div key={secao} className="mb-7">
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-400 mb-3">
              {secao}
            </h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {itens.map((m) => (
                <button
                  key={m.id}
                  onClick={() => setSel(m)}
                  className="text-left bg-white rounded-xl border border-slate-200 p-4 hover:shadow-md hover:border-primary-200 transition-all"
                >
                  <div className="flex items-start justify-between">
                    <span className="text-2xl">{m.icon}</span>
                    {m.badge && (
                      <span className="text-[10px] font-bold bg-success-100 text-success-700 px-2 py-0.5 rounded-full">
                        {m.badge}
                      </span>
                    )}
                  </div>
                  <p className="font-semibold text-slate-800 text-sm mt-2">
                    {m.title}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">
                    {m.sub}
                  </p>
                  <span className="inline-flex items-center gap-1 text-xs text-primary-600 mt-2 font-medium">
                    Ver tutorial <ChevronRight size={13} />
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
