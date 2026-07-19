// src/components/GuiaTrabalhista.tsx
// Guia Operacional de Direito do Trabalho — referência interna De Paula Teixeira.
// Accordions + checklist localStorage. Mesmo conteúdo alimenta o RAG.
import { useEffect, useState } from "react";
import {
  BookOpen,
  Clock,
  ListChecks,
  Scale,
  AlertTriangle,
  Calculator,
  FileText,
  Briefcase,
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
  "Identificar vínculo empregatício: CLT, terceirizado, autônomo, sócio disfarçado?",
  "Calcular data de admissão, demissão e tempo de serviço exato",
  "Verificar modalidade de rescisão: sem justa causa, por justa causa, pedido de demissão, rescisão indireta, comum acordo",
  "Calcular prescrição: bienal (2 anos da extinção) + quinquenal (5 anos retroativos)",
  "Levantar documentos: CTPS, holerites (últimos 12), TRCT, FGTS (extrato), aviso prévio",
  "Verificar se houve pagamento de verbas rescisórias (checar multa 477 §8º se atraso)",
  "Conferir depósitos FGTS (extrato FGTS via app FGTS ou Caixa) — ação de cobrança prescreve em 30 anos (FGTS 29)",
  "Verificar horas extras: cartão de ponto x holerites; banco de horas é válido somente por CCT/ACT",
  "Verificar adicional noturno (20% entre 22h e 5h — CLT 73)",
  "Verificar insalubridade/periculosidade: laudo técnico necessário; insalubridade grau máximo = 40% s/ SM",
  "Identificar dano moral: assédio, revista íntima, revista de pertences, humilhação pública, doença ocupacional",
  "Verificar doença ocupacional: CAT emitida? NTEP (Nexo Técnico Epidemiológico)?",
  "Confirmar competência: Vara do Trabalho da localidade da prestação de serviços (CLT 651)",
  "Calcular depósito recursal se for reclamar (em 2025: ~R$ 13.500 para RO; ~R$ 27.000 para RE)",
];

export default function GuiaTrabalhista() {
  const [marcados, setMarcados] = useState<Record<number, boolean>>({});
  useEffect(() => {
    try {
      setMarcados(
        JSON.parse(localStorage.getItem("guia_trabalhista_chk") || "{}"),
      );
    } catch {}
  }, []);
  const toggle = (i: number) => {
    const novo = { ...marcados, [i]: !marcados[i] };
    setMarcados(novo);
    localStorage.setItem("guia_trabalhista_chk", JSON.stringify(novo));
  };
  const feitos = Object.values(marcados).filter(Boolean).length;

  return (
    <div className="card p-4 mb-4 border-l-4 border-success-500">
      <div className="flex items-center gap-2 mb-1">
        <BookOpen size={16} className="text-bronze" />
        <h2 className="font-serif font-semibold text-navy text-sm">
          Guia Operacional de Direito do Trabalho
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Referência interna (prescrição, verbas rescisórias, prazos processuais,
        teses). Alimenta também o Assistente IA e o Motor de Teses. Calcule
        prescrição bienal imediatamente ao receber o caso.
      </p>

      {/* No sistema — ferramenta de liquidação de sentença */}
      <div className="mb-3 rounded-lg border border-gold-light bg-gold-50/60 p-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="text-[10px] font-semibold uppercase text-slate-400">
          No sistema
        </span>
        <span className="text-slate-600 flex-1 min-w-[200px]">
          <b className="text-navy">Liquidação de Sentença Trabalhista</b> —
          monte as verbas deferidas e obtenha a planilha consolidada (FGTS +
          multa de 40%, correção ADC 58/59 com Selic real do BCB e honorários
          CLT 791-A).
        </span>
        <a
          href="#liquidacao-trabalhista"
          onClick={(e) => {
            e.preventDefault();
            document
              .getElementById("liquidacao-trabalhista")
              ?.scrollIntoView({ behavior: "smooth" });
          }}
          className="text-gold-700 hover:text-gold-600 underline decoration-gold-200 underline-offset-2 font-medium"
        >
          Abrir ferramenta ↑
        </a>
      </div>

      <div className="space-y-2">
        <Sec icon={Clock} titulo="Prazos críticos e prescrição" aberto>
          <Tab
            head={["Prazo", "Contagem", "Base"]}
            rows={[
              [
                "Prescrição bienal",
                "2 anos da extinção do contrato",
                "CLT 7º XXIX + Súm. 308 TST",
              ],
              [
                "Prescrição quinquenal",
                "5 anos retroativos (limite: extinção)",
                "CLT 7º XXIX",
              ],
              [
                "FGTS prescrição",
                "30 anos (até RE 709.212) → bienal+quinquenal",
                "STF RE 709.212",
              ],
              [
                "Aviso prévio proporcional",
                "30d + 3d por ano trabalhado (máx. 90d)",
                "Lei 12.506/2011",
              ],
              [
                "Prazo para homologação",
                "10 dias da notificação",
                "CLT 477 §6º",
              ],
              [
                "Multa rescisória atraso",
                "Quando pago após o décimo dia",
                "CLT 477 §8º — 1 mês salário",
              ],
              [
                "Recurso ordinário (RO)",
                "8 dias do ciente da sentença",
                "CLT 895",
              ],
              ["Embargos de declaração", "5 dias da ciência", "CLT 897-A"],
              [
                "Recurso de revista (RR)",
                "8 dias do acórdão do TRT",
                "CLT 896",
              ],
              [
                "Depósito FGTS ação",
                "8 dias para depósito recursal",
                "CLT 899 §1º",
              ],
              [
                "Execução (liquidação)",
                "Após trânsito em julgado — imediata",
                "CLT 879",
              ],
            ]}
          />
          <p className="text-warn-700 mt-2">
            ⚠ Prescrição intercorrente: TST aplica Art. 11-A CLT (2 anos de
            inércia na execução). Monitore a fase de execução.
          </p>
        </Sec>

        <Sec icon={Calculator} titulo="Verbas rescisórias por modalidade">
          <Tab
            head={["Verba", "SCJC", "CJCJ", "PD", "RI", "CA"]}
            rows={[
              ["Saldo de salário", "✓", "✓", "✓", "✓", "✓"],
              ["Aviso prévio (indenizado)", "✓", "✗", "✗ (1)", "✓", "✓ (2)"],
              ["13º proporcional", "✓", "✓", "✓", "✓", "✓"],
              ["Férias vencidas + 1/3", "✓", "✓", "✓", "✓", "✓"],
              ["Férias proporcionais + 1/3", "✓", "✗ (3)", "✗", "✓", "✓"],
              ["Multa 40% FGTS", "✓", "✗", "✗", "✓", "20% (4)"],
              ["FGTS (levantamento)", "✓", "✗", "✗", "✓", "✓"],
            ]}
          />
          <p className="text-[10px] text-slate-500 mt-1">
            SCJC=Sem Causa Justa (empresa) · CJCJ=Com Justa Causa (empresa) ·
            PD=Pedido de Demissão · RI=Rescisão Indireta · CA=Comum Acordo (Lei
            13.467). (1) trabalhador cumpre ou indeniza; (2) 50% do aviso; (3)
            STF I-TSST Súm.171: férias prop. cabem só em contrato ≥1 ano ou
            rescisão indireta; (4) multa 20% + 20% do governo = 40% total.
          </p>
        </Sec>

        <Sec icon={FileText} titulo="Teses e fundamentos por matéria">
          <p>
            <b>Vínculo empregatício (CLT 2º+3º):</b> provar subordinação,
            habitualidade, pessoalidade e onerosidade. Pejotização ilícita →
            reconhecimento + diferenças (CLT 9º). Prova: trocas de WhatsApp,
            e-mails com horário, testemunhos, recibos. Ação declaratória de
            vínculo + reclamação trabalhista.
          </p>
          <p>
            <b>Horas extras:</b> art. 7º XIII CF/88 + CLT 59. Cartão de ponto
            britânico é inválido (Súm. 338 TST). Banco de horas sem CCT/ACT é
            inválido. Taxa: +50% (ordinária), +100% (domingos/feriados).
            Integração ao salário após habitualidade (Súm. 291 TST).
          </p>
          <p>
            <b>Equiparação salarial (CLT 461):</b> mesmo empregador, mesma
            função, mesmo local, diferença ≤2 anos, sem quadro de carreira.
            Paradigma deve existir na data do pedido (OJ 22 SDI-1). Reforma
            2017: quadro de carreira homologado faz cessar a equiparação.
          </p>
          <p>
            <b>Rescisão indireta (CLT 483):</b> descumprimento pelo empregador:
            não pagar, exigir serviço ilícito, assédio, redução unilateral.
            Provar com comunicação formal prévia. Efeitos = dispensa sem justa
            causa. STF: não exige a preexistência de recusa formal (precedente
            de 2024).
          </p>
          <p>
            <b>Acidente/doença do trabalho (Lei 8.213/91 + CLT 118):</b>{" "}
            estabilidade de 12 meses após alta do INSS. CAT é prova, não
            requisito. NTEP cria presunção relativa do nexo (Dec. 6.042/2007).
            Dano moral + material + estético possíveis (CC 944). Empregador
            responde objetivamente se atividade de risco (CC 927 §único + STF RE
            828.040).
          </p>
          <p>
            <b>Assédio moral (Lei 14.457/2022 + Prot. CIPA):</b> conduta abusiva
            repetida. Prova: e-mails, testemunhas, registro médico, histórico de
            metas impossíveis. Responsabilidade solidária quando há omissão da
            empresa. Indenização: critério proporcional (gravidade, cargo,
            duração).
          </p>
          <p>
            <b>Terceirização (Lei 13.429/2017):</b> responsabilidade subsidiária
            da tomadora (Súm. 331 TST). Terceirização ilícita de atividade-fim
            pode ser questionada em face de contratos anteriores à reforma; após
            2017, é lícita mas subsidiária permanece. OJs do TST: tomadora deve
            ser acionada na mesma ação.
          </p>
        </Sec>

        <Sec icon={Scale} titulo="Rito processual e fase de execução">
          <p>
            <b>Petição inicial (CLT 840):</b> pode ser verbal ou escrita; deve
            ter endereço, qualificação, pedidos específicos com valor (desde
            reforma 2017 — sem valor não tem base de cálculo de
            custas/depósito). Comissão de Conciliação Prévia (CCPv) não é mais
            obrigatória (STF ADI 2.139).
          </p>
          <p>
            <b>Audiência única (CLT 849):</b> conciliação → instrução →
            julgamento. Parte ausente à audiência inicial: reclamante →
            arquivamento; reclamado → revelia (CLT 844). Preposto deve ter
            vínculo (empregado ou sócio — Súm. 377 TST), salvo empresas
            pequenas.
          </p>
          <p>
            <b>Honorários advocatícios:</b> desde reforma (CLT 791-A):
            sucumbência de 5% a 15% pelo valor da condenação; sem condenação do
            reclamante que tiver gratuidade judicial. Honorários periciais: CLT
            790-B, adiantados pelo sucumbente na perícia.
          </p>
          <p>
            <b>Execução trabalhista:</b> liquidação por artigos ou cálculo.
            Penhora preferencial: dinheiro (SISBAJUD) → veículos (RENAJUD) →
            imóveis. Cálculo de crédito: TRCT + juros 1% a.m. (CLT 883) +
            correção IPCA-E (STF ADC 58 — afastou TR). Empresa em recuperação:
            créditos trabalhistas → fila especial (Lei 11.101/05 art. 54, limite
            150 SM).
          </p>
          <p>
            <b>Gratuidade da justiça:</b> basta declaração de hipossuficiência
            (CLT 790 §3º) ou renda ≤40% teto INSS. Após reforma: sucumbência
            pode ser cobrada do beneficiário se vencer outros pedidos.
          </p>
        </Sec>

        <Sec
          icon={Briefcase}
          titulo="Reforma Trabalhista (Lei 13.467/2017) — pontos-chave"
        >
          <Tab
            head={["Tema", "Antes", "Depois da reforma"]}
            rows={[
              [
                "Teletrabalho",
                "Sem regulação",
                "CLT 75-A: contrato escrito, despesas acordadas",
              ],
              [
                "Banco de horas",
                "CCT/ACT + 6 meses",
                "Individual escrito (máx. 6 meses) ou CCT/ACT",
              ],
              [
                "Férias parceladas",
                "2 períodos (1 ≥10d)",
                "3 períodos (1 ≥14d + 2 ≥5d cada)",
              ],
              [
                "Jornada 12×36",
                "Irregular (negociada)",
                "Lícita por lei — saúde: CCT/ACT (STF)",
              ],
              [
                "Terceirização",
                "Atividade-meio",
                "Qualquer atividade (Lei 13.429)",
              ],
              [
                "Acordo individual",
                "Vedado para redução",
                "Lícito em muitos temas (CLT 611-A)",
              ],
              [
                "Contribuição sindical",
                "Obrigatória (1 dia salário)",
                "Facultativa (STF ADI 5.938)",
              ],
              [
                "Dano extrapatrimonial",
                "Arbitrado",
                "Tabelado: ofensa leve 3SM → gravíssima 50SM",
              ],
            ]}
          />
          <p className="text-warn-700 mt-1">
            ⚠ O tabelamento de dano moral foi declarado inconstitucional pelo
            STF (ADI 6.050, 2021) para situações de dano acima do mínimo — juiz
            pode arbitrar acima da tabela.
          </p>
        </Sec>

        <Sec
          icon={ListChecks}
          titulo={`Checklist do caso trabalhista (${feitos}/${CHECKLIST.length})`}
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
        Instrumento interno. Verificar jurisprudência TST/STF atualizada.
        Depósitos recursais: atualizar pelos índices CGJT (publicados
        semestralmente).
      </p>
    </div>
  );
}
