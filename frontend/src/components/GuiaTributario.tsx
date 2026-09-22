import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  BookOpen,
  Building2,
  Clock,
  FileText,
  Landmark,
  ListChecks,
  Scale,
  ShieldCheck,
} from "lucide-react";
import {
  CHECKLIST_TRIBUTARIO,
  FONTES_OFICIAIS_GUIA,
  GUIA_TRIBUTARIO_DATA_BASE,
  REGRAS_CARF,
  REGRAS_CREDITOS,
  REGRAS_CTN_2026,
  REGRAS_JUDICIAIS,
  REGRAS_MG,
  REGRAS_MUNICIPAIS,
  REGRAS_PAF_FEDERAL,
  type RegraGuiaTributario,
} from "../lib/tributarioGuiaNormativo";

function Sec({
  icon: Icon,
  titulo,
  children,
  aberto = false,
}: {
  icon: typeof BookOpen;
  titulo: string;
  children: ReactNode;
  aberto?: boolean;
}) {
  return (
    <details
      open={aberto}
      className="group overflow-hidden rounded-lg border border-bronze-pale"
    >
      <summary className="flex cursor-pointer select-none items-center gap-2 bg-bronze-50/40 px-4 py-2.5 text-sm font-medium text-navy-900 hover:bg-bronze-50">
        <Icon size={15} className="text-bronze" />
        {titulo}
        <span className="ml-auto text-slate-400 transition-transform group-open:rotate-180">
          ▾
        </span>
      </summary>
      <div className="space-y-3 px-4 py-3 text-xs leading-relaxed text-slate-700">
        {children}
      </div>
    </details>
  );
}

function Regras({ regras }: { regras: readonly RegraGuiaTributario[] }) {
  return (
    <div className="space-y-2">
      {regras.map((item) => (
        <div
          key={item.tema}
          className="rounded-lg border border-slate-100 bg-slate-50/50 p-3"
        >
          <p className="font-semibold text-navy">{item.tema}</p>
          <p className="mt-1 text-slate-700">{item.regra}</p>
          <p className="mt-1 text-[11px] text-slate-500">
            <b>Fonte:</b> {item.fonte}
          </p>
          {item.alerta && (
            <p className="mt-2 rounded-md border border-warn-200 bg-warn-50 px-2 py-1.5 text-[11px] text-warn-900">
              <b>Atenção:</b> {item.alerta}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

export default function GuiaTributario() {
  const [marcados, setMarcados] = useState<Record<number, boolean>>({});

  useEffect(() => {
    try {
      setMarcados(
        JSON.parse(localStorage.getItem("guia_tributario_chk_v2") || "{}"),
      );
    } catch {
      setMarcados({});
    }
  }, []);

  const toggle = (index: number) => {
    const novo = { ...marcados, [index]: !marcados[index] };
    setMarcados(novo);
    localStorage.setItem("guia_tributario_chk_v2", JSON.stringify(novo));
  };

  const feitos = CHECKLIST_TRIBUTARIO.filter(
    (_, index) => marcados[index],
  ).length;

  return (
    <div className="card mb-4 border-l-4 border-warn-500 p-4">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <BookOpen size={16} className="text-bronze" />
        <h2 className="font-serif text-sm font-semibold text-navy">
          Guia Operacional de Direito Tributário
        </h2>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
          data-base {GUIA_TRIBUTARIO_DATA_BASE}
        </span>
      </div>

      <p className="mb-3 text-xs leading-5 text-slate-500">
        Instrumento interno de apoio. O guia não calcula prazo fatal, não
        substitui a leitura do ato de ciência e não transforma hipótese
        tributária em crédito recuperável. Toda conclusão deve registrar fonte
        oficial, vigência, ente, marco inicial e revisão profissional.
      </p>

      <div className="mb-3 rounded-lg border border-danger-200 bg-danger-50 p-3 text-xs leading-5 text-danger-900">
        <div className="flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div>
            <b>Regra de segurança:</b> nunca reutilize “30 dias” por hábito.
            Desde 2026, o PAF federal possui regra geral de 20 dias úteis para
            impugnação e recurso voluntário, com transição própria. Estados e
            municípios têm processo administrativo próprio e exigem norma
            específica. O CTN foi novamente alterado em 04/09/2026 pela LC
            236/2026.
          </div>
        </div>
      </div>

      <div className="mb-3 rounded-lg border border-gold-light bg-gold-50/60 p-3 text-xs leading-5">
        <div className="flex items-start gap-2">
          <ShieldCheck size={16} className="mt-0.5 shrink-0 text-gold-700" />
          <div>
            <b className="text-navy">Recuperação de créditos fiscais:</b>{" "}
            análise por XML/NF-e é pré-auditoria. O resultado deve ser tratado
            como oportunidade potencial e confirmado com escrituração,
            declarações, pagamentos, regime, documentação e regra jurídica
            aplicável antes de qualquer compensação, restituição ou ação. Data
            da NF-e não é termo inicial universal de prescrição/restituição.
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <Sec
          icon={ListChecks}
          titulo="1. Checklist de saneamento do caso"
          aberto
        >
          <div className="mb-2 flex items-center justify-between text-[11px] text-slate-500">
            <span>
              Marque somente o que foi efetivamente conferido no caso.
            </span>
            <span className="font-semibold text-navy">
              {feitos}/{CHECKLIST_TRIBUTARIO.length}
            </span>
          </div>
          <div className="space-y-1.5">
            {CHECKLIST_TRIBUTARIO.map((item, index) => (
              <label
                key={item}
                className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 hover:bg-slate-50"
              >
                <input
                  type="checkbox"
                  checked={Boolean(marcados[index])}
                  onChange={() => toggle(index)}
                  className="mt-0.5"
                />
                <span
                  className={
                    marcados[index] ? "text-slate-400 line-through" : ""
                  }
                >
                  {item}
                </span>
              </label>
            ))}
          </div>
        </Sec>

        <Sec
          icon={Clock}
          titulo="2. PAF Federal — prazos e transição de 2026"
          aberto
        >
          <Regras regras={REGRAS_PAF_FEDERAL} />
          <div className="rounded-lg border border-slate-200 bg-white p-3 text-[11px] leading-5 text-slate-600">
            <b>Fluxo seguro:</b> ciência comprovada → calcular prazo pela regra
            vigente → impugnação/DRJ → decisão → verificar recurso cabível e
            prazo vigente → CARF/CSRF conforme admissibilidade. Não usar prazo
            do recurso especial sem consultar o RICARF vigente.
          </div>
        </Sec>

        <Sec
          icon={ShieldCheck}
          titulo="3. CTN após LC 236/2026 — vigência 04/09/2026"
        >
          <Regras regras={REGRAS_CTN_2026} />
        </Sec>

        <Sec icon={Scale} titulo="4. CARF — voto de qualidade e recursos">
          <Regras regras={REGRAS_CARF} />
          <p className="rounded-lg border border-warn-200 bg-warn-50 p-3 text-[11px] leading-5 text-warn-900">
            O antigo texto do EJC dizia que o empate era automaticamente
            favorável ao contribuinte. Essa formulação foi removida por ser
            incompatível com a Lei 14.689/2023. Para recurso especial,
            competência, admissibilidade e rito, consultar o RICARF vigente na
            data do ato.
          </p>
        </Sec>

        <Sec
          icon={Building2}
          titulo="5. Minas Gerais — RPTA, e-PTA e competência"
        >
          <Regras regras={REGRAS_MG} />
          <p className="rounded-lg border border-slate-200 bg-white p-3 text-[11px] leading-5 text-slate-600">
            <b>Correção de competência:</b> causas tributárias federais em Minas
            Gerais pertencem à Justiça Federal da 6ª Região. O guia não usa mais
            TRF1 como referência para Minas.
          </p>
        </Sec>

        <Sec
          icon={Landmark}
          titulo="6. Municípios — Betim, Contagem, BH e outros"
        >
          <Regras regras={REGRAS_MUNICIPAIS} />
          <p className="rounded-lg border border-warn-200 bg-warn-50 p-3 text-[11px] leading-5 text-warn-900">
            O EJC não deve exibir “geralmente 30 dias” para defesa municipal. O
            prazo deve vir do Código Tributário/regulamento vigente do Município
            e do ato de ciência do caso concreto. A LC 236/2026 cria parâmetros
            nacionais mínimos e dever de atualização, mas não torna o rito local
            idêntico ao federal.
          </p>
        </Sec>

        <Sec
          icon={FileText}
          titulo="7. Judicialização, execução fiscal e repetição"
        >
          <Regras regras={REGRAS_JUDICIAIS} />
          <p className="rounded-lg border border-slate-200 bg-white p-3 text-[11px] leading-5 text-slate-600">
            Mandado de segurança, ação anulatória, declaratória e repetição de
            indébito têm pressupostos e termos iniciais próprios. O encerramento
            do processo administrativo é um fato relevante, mas não gera
            automaticamente “120 dias para MS” e “5 anos para anulatória”.
          </p>
        </Sec>

        <Sec
          icon={ShieldCheck}
          titulo="8. Recuperação de créditos — gate profissional"
        >
          <Regras regras={REGRAS_CREDITOS} />
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
              <p className="font-semibold text-navy">Pode automatizar</p>
              <p className="mt-1 text-[11px] text-slate-600">
                organização de XMLs, extração, memória preliminar, detecção de
                inconsistência e lista de documentos faltantes.
              </p>
            </div>
            <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
              <p className="font-semibold text-navy">Exige validação humana</p>
              <p className="mt-1 text-[11px] text-slate-600">
                elegibilidade, tese, período, modulação, prescrição/decadência,
                retificações, valor final e escolha da via de recuperação.
              </p>
            </div>
          </div>
        </Sec>

        <Sec icon={BookOpen} titulo="9. Fontes oficiais prioritárias">
          <ul className="space-y-1.5">
            {FONTES_OFICIAIS_GUIA.map((fonte) => (
              <li key={fonte} className="flex gap-2">
                <span className="text-gold-700">•</span>
                <span>{fonte}</span>
              </li>
            ))}
          </ul>
          <p className="rounded-lg border border-slate-200 bg-white p-3 text-[11px] leading-5 text-slate-600">
            Fonte secundária, resumo interno ou resposta de IA nunca substitui a
            publicação oficial quando a conclusão envolve prazo, exigibilidade,
            crédito, penalidade ou escolha de medida processual.
          </p>
        </Sec>
      </div>
    </div>
  );
}
