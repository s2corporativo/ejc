import React, { useState, useEffect } from "react";
import {
  BookOpen,
  Clock,
  ListChecks,
  Scale,
  AlertTriangle,
  FileText,
} from "lucide-react";

function Sec({
  title,
  icon,
  children,
  open = false,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  open?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(open);
  return (
    <div className="border border-bronze-pale rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 bg-white hover:bg-slate-50 text-left"
      >
        <span className="flex items-center gap-2 font-semibold text-slate-800">
          {icon}
          {title}
        </span>
        <span className="text-slate-400">{isOpen ? "▲" : "▼"}</span>
      </button>
      {isOpen && (
        <div className="p-4 border-t border-slate-100 bg-slate-50 space-y-3">
          {children}
        </div>
      )}
    </div>
  );
}

function Tab({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-slate-200">
            {headers.map((h, i) => (
              <th
                key={i}
                className="border border-bronze-pale px-3 py-2 text-left font-semibold"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
              {row.map((cell, j) => (
                <td key={j} className="border border-bronze-pale px-3 py-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Flow({ children }: { children: string }) {
  return (
    <pre className="text-[10px] bg-slate-50 border border-slate-100 rounded p-3 overflow-x-auto leading-relaxed whitespace-pre-wrap text-slate-700">
      {children}
    </pre>
  );
}

const CHK_KEY = "guia_adm_chk";
const ITEMS = [
  "Verificar prazo de 120 dias para Mandado de Segurança (ato coator)",
  "Conferir competência: federal, estadual ou municipal do ato coator",
  "Verificar prescrição de 5 anos para ações contra a Fazenda Pública",
  "Analisar nulidades do PAD — intimações, contraditório, ampla defesa",
  "Verificar se improbidade é na modalidade dolosa (Lei 14.230/21)",
  "Analisar equilíbrio econômico-financeiro do contrato administrativo",
  "Verificar sanções aplicáveis e proporcionalidade (Lei 14.133/21 art. 156)",
  "Checar responsabilidade civil do Estado: nexo causal + dano + atividade estatal",
];

export default function GuiaAdministrativo() {
  const [checks, setChecks] = useState<boolean[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(CHK_KEY) || "[]");
    } catch {
      return [];
    }
  });
  useEffect(() => {
    localStorage.setItem(CHK_KEY, JSON.stringify(checks));
  }, [checks]);
  const toggle = (i: number) =>
    setChecks((prev) => {
      const n = [...prev];
      n[i] = !n[i];
      return n;
    });

  return (
    <div className="space-y-3 p-4">
      <h2 className="text-xl font-bold text-slate-700 flex items-center gap-2">
        <BookOpen size={20} /> Guia Operacional — Direito Administrativo
      </h2>

      <Sec title="Base Legal + Prazos" icon={<Scale size={16} />} open>
        <Tab
          headers={["Norma", "Tema"]}
          rows={[
            ["CF/88 art. 37", "Princípios da Administração Pública (LIMPE)"],
            ["Lei 9.784/99", "Processo Administrativo Federal (PAF)"],
            [
              "Lei 14.133/21",
              "Contratos e contratações administrativas (execução, reajuste, sanções)",
            ],
            ["Lei 14.230/21", "Nova Lei de Improbidade Administrativa"],
            [
              "Lei 12.846/13 (LAC)",
              "Anticorrupção — responsabilidade objetiva da PJ",
            ],
            ["Lei 12.016/09", "Mandado de Segurança"],
            ["Lei 4.717/65", "Ação Popular"],
            ["Lei 7.347/85", "Ação Civil Pública"],
            ["Dec.-Lei 3.365/41", "Desapropriação por utilidade pública"],
            [
              "Lei 5.172/66 (CTN) art. 174",
              "Prescrição fiscal — 5 anos do lançamento",
            ],
          ]}
        />
        <Tab
          headers={["Prazo", "Ato", "Base"]}
          rows={[
            [
              "120 dias",
              "Mandado de Segurança (a contar do ato coator)",
              "Lei 12.016/09 art. 23",
            ],
            [
              "5 anos",
              "Prescrição de ações contra a Fazenda Pública",
              "Dec. 20.910/32 art. 1º",
            ],
            [
              "5 anos",
              "Prescrição de penalidades administrativas (PAF)",
              "Lei 9.873/99 art. 1º",
            ],
            [
              "10 dias",
              "Resposta à notificação no PAF federal",
              "Lei 9.784/99 art. 26 §3º",
            ],
            [
              "30 dias",
              "Recurso administrativo federal (regra geral)",
              "Lei 9.784/99 art. 59",
            ],
          ]}
        />
      </Sec>

      <Sec
        title="Princípios e Atos Administrativos"
        icon={<FileText size={16} />}
      >
        <Flow>{`PRINCÍPIOS CONSTITUCIONAIS (CF art. 37 caput — LIMPE):
  L — Legalidade: só faz o que a lei autoriza (≠ particulares: pode tudo que a lei não proíbe)
  I — Impessoalidade: vedado favoritismo, nepotismo, promoção pessoal
  M — Moralidade: probidade, boa-fé, lealdade institucional
  P — Publicidade: atos devem ser publicados (Diário Oficial) para produzir efeitos externos
  E — Eficiência: EC 19/98; metas de desempenho; avaliação periódica

VÍCIOS DO ATO ADMINISTRATIVO (COMFIC):
  C — Competência: praticado por agente sem atribuição legal
  O — Objeto: conteúdo ilegal ou impossível
  M — Motivo: falsidade, inexistência ou inadequação dos fatos declarados
  F — Finalidade: desvio de poder (ato formalmente legal mas com fim diverso)
  I — Forma: desrespeito à forma prescrita em lei (solenidades essenciais)

ANULAÇÃO × REVOGAÇÃO:
  • Anulação: vício de legalidade → efeitos ex tunc (retroage)
  • Revogação: conveniência/oportunidade → efeitos ex nunc (futuro)
  • Autotutela: Adm. pode anular/revogar seus próprios atos (Súm. 473 STF)`}</Flow>
      </Sec>

      <Sec
        title="PAF — Processo Administrativo (Lei 9.784/99)"
        icon={<Clock size={16} />}
      >
        <Tab
          headers={["Fase / Ato", "Prazo", "Base"]}
          rows={[
            [
              "Resposta à notificação / intimação",
              "10 dias (prorrogável por igual período)",
              "Lei 9.784/99 art. 26 §3º",
            ],
            [
              "Recurso administrativo",
              "10 dias da ciência ou publicação",
              "Lei 9.784/99 art. 59",
            ],
            [
              "Decisão do recurso pela autoridade",
              "30 dias (prorrogável por 30)",
              "Lei 9.784/99 art. 59 §1º",
            ],
            [
              "Decisão final do processo",
              "30 dias após instrução (prorrogável)",
              "Lei 9.784/99 art. 49",
            ],
            [
              "Instâncias recursais",
              "Máximo 3 instâncias administrativas",
              "Lei 9.784/99 art. 57",
            ],
            [
              "Prescrição intercorrente (PAF paralisado)",
              "3 anos sem decisão após última intimação",
              "Lei 9.873/99 art. 1º-A",
            ],
          ]}
        />
        <p className="text-sm text-slate-600 mt-2">
          <strong>Garantias fundamentais no PAF:</strong> contraditório e ampla
          defesa (CF art. 5º LV); motivação obrigatória (Lei 9.784/99 art. 50);
          proibição de reformatio in pejus (art. 64 parágrafo único).
        </p>
      </Sec>

      <Sec
        title="Improbidade Administrativa — Lei 14.230/2021"
        icon={<AlertTriangle size={16} />}
      >
        <Flow>{`MUDANÇAS FUNDAMENTAIS DA LEI 14.230/21:
  1. DOLO ESPECÍFICO OBRIGATÓRIO
     → Não existe mais improbidade culposa
     → Exige: vontade livre e consciente de praticar o ato + desvantagem ao erário
     → "Erro de gestão" e "má gestão" NÃO configuram improbidade

  2. LEGITIMIDADE EXCLUSIVA DO MP
     → Apenas o Ministério Público pode propor AIA
     → Pessoa jurídica prejudicada: não mais legitimada para propor
     → Terceiro que o MP não propõe: comunicação ao TCU / TCE

  3. PRESCRIÇÃO (art. 23):
     → 8 anos do fato para propor ação
     → Prescrição intercorrente: 4 anos sem andamento processual
     → Ex-titular de cargo: 8 anos do término do mandato/cargo

  4. SANÇÕES (art. 12):
     → Perda dos bens / valores ilicitamente acrescidos + multa + inabilitação para função pública
     → Suspensão de direitos políticos: 6 a 14 anos (ato doloso que causa dano ao erário)
     → Ressarcimento: imprescritível (CF art. 37 §5º — STF RE 852.475)

  5. RETROATIVIDADE (STF ADI 6428):
     → Lei 14.230/21 retroage para fatos anteriores em benefício do réu
     → Fatos culposos anteriores: impunidade (retroage a ausência de dolo específico)`}</Flow>
      </Sec>

      <Sec title="Responsabilidade Civil do Estado" icon={<Scale size={16} />}>
        <Tab
          headers={["Teoria", "Requisitos", "Base"]}
          rows={[
            [
              "Objetiva (regra — CF art. 37 §6º)",
              "Ação estatal + dano + nexo causal (sem prova de culpa)",
              "CF art. 37 §6º",
            ],
            [
              "Subjetiva (omissão estatal)",
              "Culpa anônima do serviço (STJ: falta do serviço)",
              "STF RE 841.526",
            ],
            [
              "Teoria do risco integral",
              "Dano nuclear, terrorismo, atividade belicosa",
              "CF art. 21 XXIII d",
            ],
          ]}
        />
        <Flow>{`EXCLUDENTES DE RESPONSABILIDADE DO ESTADO:
  • Culpa exclusiva da vítima
  • Caso fortuito e força maior (quando externo à atividade estatal)
  • Fato de terceiro que rompe o nexo causal

PRAZO PRESCRICIONAL CONTRA O ESTADO:
  → 5 anos (Dec. 20.910/32) — regra geral
  → 3 anos para responsabilidade civil extracontratual (CC art. 206 §3º V)?
    → STJ: aplica-se o prazo de 5 anos (decreto especial prevalece sobre CC)

AÇÃO REGRESSIVA DO ESTADO CONTRA O AGENTE:
  → Imprescritível (STF ADI 1.252 — discussão pendente)
  → Exige dolo ou culpa do agente público`}</Flow>
      </Sec>

      <Sec title="Mandado de Segurança" icon={<FileText size={16} />}>
        <Flow>{`REQUISITOS (CF art. 5º LXIX + Lei 12.016/09):
  1. Direito líquido e certo (prova pré-constituída — documental)
  2. Ato ilegal ou abusivo de autoridade pública ou agente no exercício de função pública
  3. Prazo decadencial: 120 dias do ato coator (art. 23)

COMPETÊNCIA:
  → Atos de prefeito / secretário municipal: TJMG (1ª instância)
  → Atos de governador / secretário estadual: TJMG (competência originária)
  → Atos de ministro / autoridade federal: TRF ou STJ (depende da hierarquia)
  → Atos do STJ: STF

LIMINAR NO MS (art. 7º III):
  → Requisitos: fumus boni iuris + periculum in mora
  → Vedada em casos que esgotam o mérito
  → Juízo pode exigir caução (art. 7º §2º)

MS PREVENTIVO:
  → Cabe quando há ameaça de ato ilegal (justo receio)
  → Não precisa esperar o dano consumado

LIMITES:
  → Não cabe para questionar lei em tese (Súm. 266 STF)
  → Não cabe contra decisão judicial transitada em julgado
  → Não substitui recurso previsto em lei (Súm. 267 STF)`}</Flow>
      </Sec>

      <Sec
        title="Anticorrupção — Lei 12.846/2013"
        icon={<AlertTriangle size={16} />}
      >
        <Tab
          headers={["Aspecto", "Regra", "Base"]}
          rows={[
            [
              "Responsabilidade da PJ",
              "Objetiva — sem necessidade de provar culpa da empresa",
              "LAC art. 2º",
            ],
            [
              "Sanção administrativa",
              "Multa de 0,1% a 20% do faturamento bruto + publicação da condenação",
              "LAC art. 6º",
            ],
            [
              "Sanção judicial (ACP do MP)",
              "Dissolução compulsória + proibição de receber benefícios públicos por 3 anos",
              "LAC art. 19",
            ],
            [
              "Acordo de Leniência",
              "Redução de multa em até 2/3 + publicação menos extensa",
              "LAC arts. 16-17",
            ],
            [
              "Prescrição",
              "5 anos da ciência da infração pela autoridade competente",
              "LAC art. 25",
            ],
            [
              "Cadastro de empresas punidas",
              "CNEP — Cadastro Nacional de Empresas Punidas",
              "LAC art. 22",
            ],
            [
              "Programa de integridade",
              "Atenuante: reduz sanção em até 4% do faturamento",
              "Dec. 8.420/15 art. 18",
            ],
          ]}
        />
      </Sec>

      <Sec title="Checklist Administrativo" icon={<ListChecks size={16} />}>
        <div className="space-y-2">
          {ITEMS.map((item, i) => (
            <label
              key={i}
              className="flex items-start gap-2 cursor-pointer text-sm"
            >
              <input
                type="checkbox"
                checked={!!checks[i]}
                onChange={() => toggle(i)}
                className="mt-0.5"
              />
              <span
                className={
                  checks[i] ? "line-through text-slate-400" : "text-slate-700"
                }
              >
                {item}
              </span>
            </label>
          ))}
          <p className="text-xs text-slate-400">
            {checks.filter(Boolean).length}/{ITEMS.length} itens concluídos
          </p>
        </div>
      </Sec>
    </div>
  );
}
