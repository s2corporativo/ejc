// ── src/components/GuiaEmpresarial.tsx ───────────────────────────────────────
// Guia Operacional de Direito Empresarial (De Paula Teixeira). Referência
// interna em accordions + checklist interativo. O mesmo conteúdo está no RAG,
// então o Assistente/Motor de Teses também o usa. Tudo exige revisão do
// advogado.
import { useEffect, useState } from "react";
import {
  BookOpen,
  Building2,
  FileText,
  Gavel,
  Scale,
  ShieldCheck,
  Wrench,
  ListChecks,
  AlertTriangle,
} from "lucide-react";

function Sec({ icon: Icon, titulo, children, aberto = false }: any) {
  return (
    <details
      open={aberto}
      className="group border border-bronze-pale rounded-lg overflow-hidden"
    >
      <summary className="flex items-center gap-2 px-4 py-2.5 cursor-pointer bg-bronze-50/40 hover:bg-bronze-50 text-sm font-medium text-navy-900 select-none">
        <Icon size={15} className="text-bronze" /> {titulo}
        <span className="ml-auto text-slate-400 group-open:rotate-180 transition-transform">
          ▾
        </span>
      </summary>
      <div className="px-4 py-3 text-xs text-slate-700 space-y-2 leading-relaxed">
        {children}
      </div>
    </details>
  );
}

function Tab({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-left text-ink-light">
            {head.map((h) => (
              <th key={h} className="py-1 pr-3 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-bronze-50">
              {r.map((c, j) => (
                <td key={j} className="py-1 pr-3 align-top">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const CHECKLIST = [
  "Identificar a demanda (societário / contratual / M&A / trabalhista preventivo / LGPD / PI / contencioso)",
  "Obter contrato social / estatuto atualizado e última alteração registrada na Junta Comercial",
  "Verificar existência de acordo de sócios/acionistas e cláusulas de saída (Tag Along, Drag Along, Shotgun)",
  "Levantar quadro societário completo (participações, administradores, procurações vigentes)",
  "Mapear patrimônio dos sócios exposto a risco (avaliar holding patrimonial / blindagem lícita)",
  "Verificar contingências que atraem desconsideração da personalidade jurídica (CC 50, CDC 28, CLT)",
  "Em M&A: definir escopo da due diligence (jurídica, fiscal, trabalhista, ambiental) e data-room",
  "Revisar contratos comerciais vigentes (serviços, fornecimento, locação, distribuição, representação)",
  "Checar conformidade LGPD (mapeamento de dados, bases legais, termos de privacidade, DPO)",
  "Verificar registro de marcas/patentes no INPI e prazos de renovação/oposição",
  "Em execução/cobrança: conferir título, prescrição e prazo de embargos (15 dias — CPC 915)",
  "Em contencioso tributário: avaliar suspensão de exigibilidade (CTN 151) e recuperação de créditos",
  "Em conflito societário: avaliar dissolução parcial e critério de apuração de haveres (CPC 599-609)",
  "Definir modelo de honorários (projeto de alto valor agregado vs. mensalista recorrente)",
  "Registrar tudo no dossiê 360º do cliente no EJC",
];

export default function GuiaEmpresarial() {
  const [marcados, setMarcados] = useState<Record<number, boolean>>({});
  useEffect(() => {
    try {
      setMarcados(JSON.parse(localStorage.getItem("guia_emp_chk") || "{}"));
    } catch {}
  }, []);
  const toggle = (i: number) => {
    const novo = { ...marcados, [i]: !marcados[i] };
    setMarcados(novo);
    localStorage.setItem("guia_emp_chk", JSON.stringify(novo));
  };
  const feitos = Object.values(marcados).filter(Boolean).length;

  return (
    <div className="card p-4 mb-4 border-l-4 border-bronze">
      <div className="flex items-center gap-2 mb-1">
        <BookOpen size={16} className="text-bronze" />
        <h2 className="font-serif font-semibold text-navy text-sm">
          Guia Operacional de Direito Empresarial
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Referência interna (consultivo societário, rotina contratual,
        contencioso, legislação, checklist). O mesmo acervo alimenta o
        Assistente IA e o Motor de Teses. Toda aplicação ao caso concreto exige
        revisão do advogado — verificar a data e eventual superação da
        jurisprudência.
      </p>

      <div className="space-y-2">
        <Sec
          icon={Building2}
          titulo="1. Consultivo estrutural e societário (alto valor agregado)"
          aberto
        >
          <p>
            <b>Planejamento sucessório e patrimonial:</b> constituição de
            holdings familiares/patrimoniais para proteger os bens dos sócios e
            organizar a sucessão em vida, evitando o desgaste e o custo do
            inventário.
          </p>
          <p>
            <b>Constituição e reestruturação societária:</b> elaboração de
            contratos sociais complexos, estatutos, acordos de
            sócios/acionistas com cláusulas de saída e controle (Tag Along,
            Drag Along, Shotgun) e atas de assembleia.
          </p>
          <p>
            <b>Assessoria em M&A (fusões e aquisições):</b> due diligence
            (auditoria de riscos jurídica e fiscal) e contratos de compra e
            venda de participações societárias.
          </p>
          <p>
            <b>Proteção patrimonial (blindagem lícita):</b> estruturação
            jurídica legal para mitigar riscos de desconsideração da
            personalidade jurídica sobre os bens pessoais dos sócios.
          </p>
        </Sec>

        <Sec
          icon={FileText}
          titulo="2. Operacional rotineiro (receita recorrente — mensalistas)"
        >
          <p>
            <b>Engenharia contratual:</b> elaboração, revisão e negociação de
            contratos comerciais — prestação de serviços, fornecimento, locação
            comercial, distribuição e representação comercial.
          </p>
          <p>
            <b>Assessoria trabalhista preventiva:</b> revisão de contratos de
            trabalho, regulamentos internos, políticas de benefícios (ex.:
            Stock Options) e orientação para demissões de cargos de confiança.
          </p>
          <p>
            <b>Adequação à LGPD:</b> projetos de conformidade, mapeamento de
            dados corporativos e elaboração de termos de privacidade.
          </p>
          <p>
            <b>Registro de marcas e patentes:</b> gestão do portfólio de
            propriedade intelectual perante o INPI (depósito, acompanhamento,
            oposições e renovações).
          </p>
        </Sec>

        <Sec
          icon={Gavel}
          titulo="3. Contencioso especializado (defesa de interesses)"
        >
          <p>
            <b>Defesa em execuções e cobranças:</b> atuação em execuções de
            títulos extrajudiciais, ações de cobrança e recuperação de crédito.
          </p>
          <p>
            <b>Contencioso tributário:</b> impugnações administrativas e ações
            judiciais para suspender a exigibilidade de tributos indevidos ou
            recuperar créditos fiscais.
          </p>
          <p>
            <b>Dissolução de sociedade e exclusão de sócio:</b> condução de
            conflitos entre sócios, pela via judicial ou extrajudicial, com
            apuração justa de haveres.
          </p>
        </Sec>

        <Sec icon={Scale} titulo="Legislação-chave">
          <Tab
            head={["Norma", "Conteúdo"]}
            rows={[
              [
                "CC arts. 981 e ss.",
                "Direito de empresa: sociedades, administração, dissolução e resolução em relação a um sócio",
              ],
              [
                "CC art. 50",
                "Desconsideração da personalidade jurídica (desvio de finalidade / confusão patrimonial)",
              ],
              [
                "Lei 6.404/76",
                "Sociedades por ações: estatuto, acordos de acionistas, assembleias, deveres dos administradores",
              ],
              [
                "Lei 14.195/21",
                "Ambiente de negócios: facilitação de abertura de empresas e modernização societária",
              ],
              [
                "LINDB (DL 4.657/42)",
                "Segurança jurídica na aplicação do direito público e na interpretação de negócios",
              ],
              [
                "Lei 13.709/18 (LGPD)",
                "Proteção de dados pessoais: bases legais, direitos dos titulares, sanções da ANPD",
              ],
              [
                "Lei 9.279/96 (LPI)",
                "Marcas e patentes: registro, vigência e proteção perante o INPI",
              ],
              [
                "Lei 11.101/05",
                "Recuperação judicial, extrajudicial e falência",
              ],
              [
                "CPC arts. 599-609",
                "Ação de dissolução parcial de sociedade e apuração de haveres",
              ],
              [
                "CPC arts. 914-920",
                "Embargos à execução (15 dias; efeito suspensivo não automático)",
              ],
              [
                "CTN art. 151",
                "Hipóteses de suspensão da exigibilidade do crédito tributário",
              ],
            ]}
          />
        </Sec>

        <Sec icon={ShieldCheck} titulo="Prazos e atenções típicas">
          <Tab
            head={["Situação", "Prazo / atenção", "Base"]}
            rows={[
              [
                "Embargos à execução",
                "15 dias da juntada da citação",
                "CPC 915",
              ],
              [
                "Registro de atos societários com efeito retroativo",
                "30 dias da assinatura",
                "CC 1.151 §1º / Lei 8.934/94 art. 36",
              ],
              [
                "Direito de retirada (sociedade por prazo indeterminado)",
                "Notificação com 60 dias de antecedência",
                "CC 1.029",
              ],
              [
                "Oposição a pedido de registro de marca",
                "60 dias da publicação na RPI",
                "LPI art. 158",
              ],
              [
                "Vigência do registro de marca",
                "10 anos, prorrogáveis",
                "LPI art. 133",
              ],
              [
                "Pretensões entre sócios / contra administradores",
                "Regra geral 3 anos (verificar hipótese)",
                "CC 206 §3º",
              ],
              [
                "Repetição de indébito tributário",
                "5 anos",
                "CTN 168",
              ],
            ]}
          />
          <p className="text-warn-700">
            ⚠ Prazos societários e de PI variam por hipótese — sempre conferir
            a norma vigente e o caso concreto antes de assumir o prazo.
          </p>
        </Sec>

        <Sec icon={Wrench} titulo="Ferramentas do sistema (EJC)">
          <p>
            <b>Contratos societários:</b> use os modelos e o módulo de Peças do
            EJC para minutas de contrato social, alterações, acordos de sócios
            e atas — sempre como rascunho sujeito a revisão do advogado.
          </p>
          <p>
            <b>Dossiê 360º do cliente:</b> centralize quadro societário,
            contratos vigentes, contingências e marcas/patentes no cadastro do
            cliente PJ, para alimentar due diligence e o Assistente IA.
          </p>
          <p>
            <b>Ferramentas do ramo:</b> prazos de recuperação judicial,
            verificação de notificação ao CADE e cálculo de juros de mora estão
            disponíveis nas calculadoras desta página.
          </p>
        </Sec>

        <Sec
          icon={ListChecks}
          titulo={`Checklist do caso empresarial (${feitos}/${CHECKLIST.length})`}
        >
          <div className="space-y-1.5">
            {CHECKLIST.map((item, i) => (
              <label key={i} className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!marcados[i]}
                  onChange={() => toggle(i)}
                  className="mt-0.5"
                />
                <span
                  className={
                    marcados[i]
                      ? "line-through text-slate-400"
                      : "text-slate-700"
                  }
                >
                  {item}
                </span>
              </label>
            ))}
          </div>
        </Sec>
      </div>

      <p className="text-[10px] text-warn-700 mt-3 flex items-start gap-1">
        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
        Instrumento de trabalho interno. Legislação e jurisprudência sujeitas a
        atualização — confirmar a data e eventual superação antes de aplicar.
      </p>
    </div>
  );
}
