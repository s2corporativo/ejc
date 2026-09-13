import {
  AlertTriangle,
  ChevronRight,
  ExternalLink,
  Gavel,
  Radar,
} from "lucide-react";
import { Link } from "react-router";

type AlertKind =
  "Jurisprudência" | "Repetitivo" | "Precedente administrativo" | "Legislação";

type LegalAlert = {
  id: string;
  tribunal: string;
  referencia: string;
  data: string;
  area: string;
  prioridade: "P0" | "P1";
  kind: AlertKind;
  estado: string;
  titulo: string;
  resumo: string;
  impacto: string;
  acao: string;
  fonte: string;
};

/**
 * Bootstrap curado do Radar Jurídico no dashboard principal.
 *
 * Os registros abaixo foram conferidos em fontes oficiais em 07/09/2026.
 * Eles são somente informativos e não alteram teses, casos, processos ou
 * peças automaticamente. A decisão de revisão/validação permanece humana.
 * Quando o Radar Jurisprudencial canônico persistir eventos, este componente
 * deve consumir essa API em vez desta curadoria estática.
 */
const ALERTAS: LegalAlert[] = [
  {
    id: "stj-tema-1177",
    tribunal: "STJ",
    referencia: "Tema 1.177",
    data: "01/09/2026",
    area: "Processo Civil / Coletivo",
    prioridade: "P0",
    kind: "Jurisprudência",
    estado: "Repetitivo julgado — tese vinculante",
    titulo: "ACP sindical: honorários sucumbenciais contra a União",
    resumo:
      "A Primeira Seção fixou que, por simetria, a isenção do art. 18 da Lei 7.347/1985 impede a condenação da União, quando vencida em ação civil pública ajuizada por sindicato, ao pagamento de honorários sucumbenciais, salvo comprovada má-fé.",
    impacto:
      "Enfraquece teses de ataque que peçam honorários contra a União apenas pela procedência da ACP e fortalece a defesa fazendária.",
    acao: "Criar/atualizar a tese ACP > sindicato > honorários > União e marcar como repetitivo obrigatório (CPC, art. 927, III).",
    fonte: "https://scon.stj.jus.br/SCON/GetPDFINFJ?edicao=0899",
  },
  {
    id: "stj-tema-1473",
    tribunal: "STJ",
    referencia: "Tema 1.473",
    data: "31/08/2026",
    area: "Tributário / Simples Nacional",
    prioridade: "P1",
    kind: "Repetitivo",
    estado: "Afetado — tese de mérito ainda não fixada",
    titulo: "Gorjetas e base de cálculo do Simples Nacional",
    resumo:
      "A Primeira Seção afetou os REsp 2.239.211/PE, 2.239.811/PB e 2.261.206/CE para definir se gorjetas recebidas e repassadas aos empregados integram a base de cálculo do Simples Nacional.",
    impacto:
      "A matéria deve ser tratada como controvertida; não é seguro apresentar inclusão ou exclusão das gorjetas como entendimento consolidado.",
    acao: "Cadastrar como PENDING_BINDING_PRECEDENT e disparar revalidação quando o mérito do repetitivo for julgado.",
    fonte: "https://scon.stj.jus.br/SCON/GetPDFINFJ?edicao=0899",
  },
  {
    id: "tcu-acordao-2321-2026",
    tribunal: "TCU",
    referencia: "Acórdão 2321/2026-Plenário",
    data: "02/09/2026",
    area: "Administrativo / Licitações",
    prioridade: "P0",
    kind: "Precedente administrativo",
    estado: "Precedente administrativo relevante",
    titulo: "Conflito de interesses e avaliação objetiva de amostras",
    resumo:
      "O TCU reconheceu conflito de interesses em licitação com participação de empresa do mesmo grupo econômico de prestadora de apoio técnico ao órgão e apontou vícios na avaliação de amostras realizada sem critérios objetivos e somente na fase recursal.",
    impacto:
      "Fortalece impugnações e recursos sobre impedimento objetivo, segregação de funções e nulidade de avaliação de amostras sem critérios previamente definidos.",
    acao: "Criar/atualizar teses sobre arts. 9º e 14 da Lei 14.133/2021 e sobre critérios objetivos para amostras; não classificar como precedente judicial vinculante.",
    fonte:
      "https://pesquisa.apps.tcu.gov.br/resultado/acordao-completo/Integridade",
  },
  {
    id: "decreto-13108-2026",
    tribunal: "PRESIDÊNCIA DA REPÚBLICA",
    referencia: "Decreto 13.108/2026",
    data: "01/09/2026",
    area: "Consumidor / Eventos",
    prioridade: "P1",
    kind: "Legislação",
    estado: "Norma nova — vigência parcialmente escalonada",
    titulo: "Comercialização de ingressos para eventos",
    resumo:
      "O decreto regulamenta o CDC para venda de ingressos, inclusive em sites e aplicativos, com deveres de transparência, prevenção de aquisição massiva automatizada, rastreabilidade e repressão à revenda especulativa.",
    impacto:
      "Cria novos fundamentos normativos para teses de consumidor sobre taxas, transparência, segurança, revenda e responsabilidade de comercializadores de ingressos.",
    acao: "Criar o núcleo Consumidor > Eventos > Ingressos e observar a vigência específica dos dispositivos antes de usar a norma em peças.",
    fonte:
      "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/d13108.htm",
  },
  {
    id: "decreto-13109-2026",
    tribunal: "PRESIDÊNCIA DA REPÚBLICA",
    referencia: "Decreto 13.109/2026",
    data: "01/09/2026",
    area: "Consumidor / Eventos",
    prioridade: "P1",
    kind: "Legislação",
    estado: "Norma vigente",
    titulo: "Acesso à água potável em eventos",
    resumo:
      "O decreto garante entrada com recipientes de água, sujeita a restrições de segurança, e exige disponibilização gratuita de água potável em eventos com previsão superior a mil participantes.",
    impacto:
      "Reforça teses consumeristas e de responsabilidade de organizadores de eventos, inclusive quanto a práticas abusivas e dever de segurança.",
    acao: "Adicionar ao Banco de Teses de consumidor/eventos e relacionar a responsabilidade civil, administrativa e aos deveres de informação e segurança.",
    fonte:
      "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/d13109.htm",
  },
];

function prioridadeClasses(prioridade: LegalAlert["prioridade"]) {
  if (prioridade === "P0") {
    return "bg-red-50 text-red-700 dark:bg-red-400/10 dark:text-red-200";
  }
  return "bg-amber-50 text-amber-800 dark:bg-amber-400/10 dark:text-amber-200";
}

export default function JurisprudentialAlertsStrip() {
  return (
    <section
      aria-labelledby="alertas-juridicos-title"
      className="ejc-legal-rail"
    >
      <header className="ejc-legal-rail__header">
        <div className="ejc-legal-rail__heading">
          <span className="ejc-legal-rail__icon">
            <Gavel aria-hidden="true" />
          </span>
          <div>
            <div className="ejc-legal-rail__title-row">
              <h2 id="alertas-juridicos-title">Radar Jurídico</h2>
              <span>{ALERTAS.length}</span>
            </div>
            <p>Atualizações legais e precedentes relevantes</p>
          </div>
        </div>
        <Link to="/dpt360/radar" className="ejc-legal-rail__open">
          Abrir radar <ChevronRight aria-hidden="true" />
        </Link>
      </header>

      <div
        className="ejc-legal-rail__feed"
        role="feed"
        aria-label="Atualizações jurídicas"
      >
        {ALERTAS.map((alerta) => (
          <article key={alerta.id} className="ejc-legal-rail__item">
            <div className="ejc-legal-rail__meta">
              <span className={prioridadeClasses(alerta.prioridade)}>
                {alerta.prioridade}
              </span>
              <span>{alerta.kind}</span>
              <time>{alerta.data}</time>
            </div>
            <p className="ejc-legal-rail__source">
              {alerta.tribunal} · {alerta.referencia}
            </p>
            <h3>{alerta.titulo}</h3>
            <p className="ejc-legal-rail__summary">{alerta.resumo}</p>

            <details className="ejc-legal-rail__details">
              <summary>Impacto e ação recomendada</summary>
              <div>
                <p>
                  <strong>Impacto:</strong> {alerta.impacto}
                </p>
                <p>
                  <strong>Ação:</strong> {alerta.acao}
                </p>
                <p>
                  <strong>Estado:</strong> {alerta.estado}
                </p>
              </div>
            </details>

            <a
              href={alerta.fonte}
              target="_blank"
              rel="noreferrer"
              className="ejc-legal-rail__official"
            >
              Fonte oficial <ExternalLink aria-hidden="true" />
            </a>
          </article>
        ))}
      </div>

      <footer className="ejc-legal-rail__footer">
        <AlertTriangle aria-hidden="true" />
        <span>
          Informativo. Nenhum item altera tese, caso ou peça sem validação
          humana.
        </span>
      </footer>
    </section>
  );
}
