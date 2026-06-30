// src/components/GuiaPrevidenciario.tsx
// Guia Operacional de Direito Previdenciário — referência interna De Paula Teixeira.
import { useEffect, useState } from "react";
import {
  BookOpen,
  Clock,
  ListChecks,
  Scale,
  AlertTriangle,
  Heart,
  FileText,
  Users,
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
  "Identificar o benefício negado ou a revisar: espécie, competência INSS ou JEF?",
  "Calcular prescrição: 5 anos das parcelas vencidas (Decreto 20.910/32 + Súmula 85 STJ)",
  "Verificar se o requerimento administrativo foi feito e negado (condição de procedibilidade — STJ)",
  "Levantar CNIS do cliente (Cadastro Nacional de Informações Sociais) via Meu INSS",
  "Identificar qualidade de segurado: empregado, contribuinte individual, avulso, segurado especial",
  "Verificar tempo de contribuição e carência exigida pelo benefício",
  "Conferir data de início da incapacidade (DII) ou data do óbito no caso de pensão por morte",
  "Verificar se houve cessação indevida de benefício — prazo: 30 dias para recurso na Junta de Recursos",
  "Coletar laudos médicos, atestados e perícias anteriores para instrução da perícia judicial",
  "Verificar direito ao BPC/LOAS: pessoa com deficiência ou idoso ≥65 anos + renda familiar ≤1/4 SM p/ membro",
  "Verificar competência: JEF (≤60 SM) ou JF comum (acima); Justiça Estadual em comarcas sem JF",
  "Calcular juros e correção: IPCA-E + juros 1% a.m. até 11/2021; pós-EC 113/2021 = Selic",
];

export default function GuiaPrevidenciario() {
  const [marcados, setMarcados] = useState<Record<number, boolean>>({});
  useEffect(() => {
    try {
      setMarcados(JSON.parse(localStorage.getItem("guia_prev_chk") || "{}"));
    } catch {}
  }, []);
  const toggle = (i: number) => {
    const novo = { ...marcados, [i]: !marcados[i] };
    setMarcados(novo);
    localStorage.setItem("guia_prev_chk", JSON.stringify(novo));
  };
  const feitos = Object.values(marcados).filter(Boolean).length;

  return (
    <div className="card p-4 mb-4 border-l-4 border-violet-500">
      <div className="flex items-center gap-2 mb-1">
        <BookOpen size={16} className="text-bronze" />
        <h2 className="font-serif font-semibold text-navy text-sm">
          Guia Operacional de Direito Previdenciário
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Referência interna (benefícios, carências, recursos, BPC/LOAS,
        revisões). Alimenta o Assistente IA e o Motor de Teses. Verificar CNIS e
        requerimento administrativo no primeiro atendimento.
      </p>

      <div className="space-y-2">
        <Sec icon={Clock} titulo="Benefícios, carências e prazos" aberto>
          <Tab
            head={["Benefício", "Carência", "Requisito principal", "Base"]}
            rows={[
              [
                "Aposentadoria por incapacidade permanente",
                "12 contribuições",
                "Incapacidade total e permanente + DII",
                "Lei 8.213/91 art. 42",
              ],
              [
                "Auxílio por incapacidade temporária",
                "12 contribuições",
                "Incapacidade > 15 dias (empresa paga os 15 primeiros)",
                "Lei 8.213/91 art. 59",
              ],
              [
                "Aposentadoria programada (pós-EC 103)",
                "15 anos F / 20 anos M",
                "65 anos F / 65 anos M (regras de transição até 2031)",
                "EC 103/2019",
              ],
              [
                "Aposentadoria por idade (rural — segurado especial)",
                "0 contribuições",
                "55 anos F / 60 anos M + atividade rural comprovada",
                "Lei 8.213/91 art. 143",
              ],
              [
                "Pensão por morte",
                "0 (acidente) / 18 contrib.",
                "Óbito do segurado + qualidade de segurado",
                "Lei 8.213/91 art. 74",
              ],
              [
                "Salário-maternidade (empregada)",
                "0 (empregada CLT)",
                "Parto/adoção — 120 dias (+ 60 dias empresa cidadã)",
                "Lei 8.213/91 art. 71",
              ],
              [
                "Salário-maternidade (individual/especial)",
                "10 contribuições",
                "Parto — 120 dias",
                "Lei 8.213/91 art. 71-B",
              ],
              [
                "BPC/LOAS (deficiente/idoso)",
                "Não é benefício previdenciário",
                "Renda familiar ≤1/4 SM p/ membro + def. ou ≥65 anos",
                "LOAS art. 20",
              ],
              [
                "Auxílio-acidente",
                "0 (acidente de trabalho)",
                "Sequela que reduz capacidade laboral — 50% SM",
                "Lei 8.213/91 art. 86",
              ],
            ]}
          />
          <Tab
            head={["Prazo processual", "Contagem", "Base"]}
            rows={[
              [
                "Prescrição das parcelas",
                "5 anos das parcelas vencidas",
                "Decreto 20.910/32 + Súmula 85 STJ",
              ],
              [
                "Recurso ao CRPS (Junta)",
                "30 dias da ciência do indeferimento/cessação",
                "Decreto 3.048/99 art. 305",
              ],
              [
                "Recurso ordinário ao CRPS",
                "30 dias da decisão da Junta",
                "Decreto 3.048/99 art. 308",
              ],
              [
                "Prazo INSS para decidir requerimento",
                "45 dias úteis (Lei 9.784/99)",
                "STJ: após esse prazo, pode ajuizar diretamente",
              ],
              [
                "Embargos à execução (JEF)",
                "30 dias da penhora",
                "Lei 10.259/01 + CPC subsidiário",
              ],
            ]}
          />
        </Sec>

        <Sec
          icon={Heart}
          titulo="Aposentadoria por incapacidade — teses e perícia"
        >
          <p>
            <b>Data de início da incapacidade (DII):</b> o laudo pericial
            judicial é soberano sobre a perícia do INSS (STJ Súmula 149 ≠ aqui;
            ver Súmula 47 TNU). Juiz pode fixar DII diferente da perícia se há
            prova documental anterior (laudos, internação, histórico médico).
            DIB = DII ou data do requerimento, o que for posterior.
          </p>
          <p>
            <b>Incapacidade parcial × total:</b> incapacidade parcial para a
            atividade habitual → reabilitação profissional antes de converter em
            invalidez. STJ: INSS deve oferecer reabilitação; se recusar,
            converte em invalidez. TNU: incapacidade para atividade habitual em
            contexto socioeconômico precário = total (Súmula 47 TNU).
          </p>
          <p>
            <b>Nexo técnico epidemiológico (NTEP — Dec. 6.042/2007):</b> ativa
            presunção relativa de vínculo entre doença e atividade. Empregador
            que discordar deve apresentar laudo contraditor. Afeta o FAP (Fator
            Acidentário de Prevenção).
          </p>
          <p>
            <b>Acidente de qualquer natureza:</b> carência zero e mantém
            qualidade de segurado pelo período de graça (12 a 36 meses
            pós-afastamento). Art. 15 Lei 8.213/91.
          </p>
          <p>
            <b>Atividade insalubre + aposentadoria especial:</b> 15 anos em
            agentes físicos (ruído {">"} 85dB), 20 anos em agentes químicos
            (asbestos, benzeno), 25 anos em agentes biológicos ou demais. Exige
            PPP (Perfil Profissiográfico Previdenciário) + LTCAT. Pós-EC 103:
            novas regras para conversão de tempo especial em comum.
          </p>
        </Sec>

        <Sec
          icon={Users}
          titulo="BPC/LOAS e pensão por morte — pontos críticos"
        >
          <p>
            <b>BPC/LOAS (Lei 8.742/93 art. 20):</b> não é previdenciário (não
            gera pensão por morte nem salário-maternidade). Critério de renda:
            renda familiar per capita ≤1/4 do salário mínimo — STJ flexibilizou
            para análise do contexto de miserabilidade (Súmula 529 STJ). Pessoa
            com deficiência: impedimento de longo prazo (≥2 anos) que obstrua
            participação social — LOAS pós-Lei 13.146/2015 (Estatuto PcD).
          </p>
          <p>
            <b>Pensão por morte:</b> mantém qualidade de segurado do
            instituidor. Dependentes: cônjuge/companheiro(a), filhos menores de
            21 ou inválidos, pais (subsidiários), irmãos (subsidiários). União
            estável comprovada: declaração + documentos de convivência. Pós-EC
            103/2019: cota individual de 50% + 10% p/ dependente (mínimo 60%;
            máximo 100%). Duração: vitalícia se cônjuge ≥45 anos ou inválido;
            transitória se {"<"}45 (de 3 a 15 anos conforme tempo de casamento).
          </p>
          <p>
            <b>Salário-maternidade e segurada especial:</b> basta demonstrar
            exercício de atividade rural nos 10 meses anteriores ao parto.
            Prova: declaração do sindicato rural, ITR, DAP, testemunhos, carnê
            de sócio cooperativa.
          </p>
        </Sec>

        <Sec icon={FileText} titulo="Revisão de benefício — teses e cálculo">
          <p>
            <b>Revisão da vida toda (STF RE 1.276.977 — Tema 1102):</b>{" "}
            possibilidade de incluir salários anteriores a julho/1994 (pré-Plano
            Real) no cálculo do benefício, se isso for mais favorável. STF
            julgou procedente por maioria (6×5) em 2022. INSS recalculando em
            lote; ação cabe se o recálculo não for feito ou for inferior ao
            pedido. Prescrição: 5 anos das diferenças.
          </p>
          <p>
            <b>
              Revisão do art. 29, II da Lei 8.213/91 (80% maiores salários):
            </b>{" "}
            cálculo original usava 80% dos maiores salários de contribuição de
            julho/1994 ao mês anterior ao benefício. Pós-fator previdenciário:
            multiplicador que reduz o benefício conforme expectativa de vida e
            tempo de contribuição. Tese: contestar aplicação do fator para quem
            já reunia todos os requisitos antes de 1999 (tempus regit actum).
          </p>
          <p>
            <b>Revisão por Erro Material (art. 103-A Lei 8.213/91):</b> sem
            prazo decadencial — pode ser requerida a qualquer tempo quando o
            erro é material (dado computado errado). Ex.: salário de
            contribuição digitado incorretamente no CNIS.
          </p>
          <p>
            <b>Decadência de 10 anos (art. 103 Lei 8.213/91):</b> para revisão
            que não seja erro material — conta da data do primeiro pagamento.
            STJ: prazo de 10 anos (não 5). Suspenso durante impugnação
            administrativa.
          </p>
          <p>
            <b>Correção monetária pós-EC 113/2021:</b> Selic (acumulada no
            período) substitui IPCA-E + juros 1% a.m. para ações ajuizadas após
            a EC. Para ações anteriores: IPCA-E + juros 1% a.m. (STF ADC 58 se
            verba trabalhista; para previdenciário, TRF aplica IPCA-E até
            10/2021 e Selic depois).
          </p>
        </Sec>

        <Sec icon={Scale} titulo="JEF — Juizado Especial Federal">
          <p>
            <b>Competência:</b> causas previdenciárias com valor ≤60 salários
            mínimos (Lei 10.259/01 art. 3º). Acima: JF comum (rito ordinário
            CPC). Em comarcas sem JF/JEF: Justiça Estadual (Lei 10.259/01 art.
            20).
          </p>
          <p>
            <b>Rito:</b> sem revelia formal do INSS; conciliação → instrução
            (perícia) → sentença. Sem honorários de sucumbência se o
            beneficiário perde (Lei 9.099/95 art. 55 subsidiário). Beneficiário
            que ganha: honorários de 10% do valor da condenação (STJ Súmula 111
            ≠ — ver regra específica JEF).
          </p>
          <p>
            <b>Tutela antecipada de urgência:</b> cabível quando há urgência
            (incapacidade grave, iminência de morte, ausência de renda). Juiz
            pode implantar o benefício provisoriamente. Reversão: INSS pode
            recorrer (recurso inominado ao TRF/TR, prazo 10 dias).
          </p>
          <p>
            <b>Cumprimento de sentença (RPV):</b> Requisição de Pequeno Valor —
            pagamento em 60 dias (CF/88 art. 100 §3º). Precatório apenas se
            acima do teto de RPV (definido anualmente por lei). Selic sobre o
            período de atraso no pagamento da RPV.
          </p>
          <p>
            <b>Recurso inominado:</b> 10 dias da sentença → Turma Recursal do
            TRF. Sem efeito suspensivo para implantação de benefício se há
            urgência. Pedido de uniformização: TNU (questão de direito material
            entre TRs de diferentes regiões).
          </p>
        </Sec>

        <Sec
          icon={ListChecks}
          titulo={`Checklist do caso previdenciário (${feitos}/${CHECKLIST.length})`}
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

      <p className="text-[10px] text-amber-700 mt-3 flex items-start gap-1">
        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
        Instrumento interno. Verificar EC 103/2019 (Reforma da Previdência),
        teses pendentes no STF/TNU e tabelas de salário mínimo vigente (BPC/LOAS
        e RPV atualizam anualmente).
      </p>
    </div>
  );
}
