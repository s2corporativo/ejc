// ── src/components/GuiaTransito.tsx ──────────────────────────────────────────
// Guia Operacional de Multas de Trânsito (De Paula Teixeira). Referência interna
// em accordions + checklist. O mesmo conteúdo está no RAG (Assistente/Motor de
// Teses também o usam). Trânsito é guiado por prazos — revisão do advogado.
import { useEffect, useState } from "react";
import {
  BookOpen,
  Clock,
  ListChecks,
  Scale,
  Gauge,
  FileWarning,
  CreditCard,
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
  "Identificar o documento recebido (NIA / NIP / decisão JARI / decisão CETRAN / suspensão de CNH)",
  "Calcular IMEDIATAMENTE todos os prazos aplicáveis",
  "Verificar se algum prazo já está vencido",
  "Verificar a data da infração → calcular prescrição (5 anos — CTB 322)",
  "Verificar se a multa já foi paga → repetição de indébito possível?",
  "Verificar pontos acumulados na CNH (DETRAN-MG)",
  "Verificar outras multas pendentes que possam causar suspensão",
  "Identificar o artigo CTB da infração e a natureza/pontos",
  "Verificar vícios formais do auto (data, hora, local, agente, equipamento)",
  "Se equipamento: número do medidor → consultar aferição/aprovação no INMETRO",
  "Solicitar fotos do auto e verificar sinalização do local (Street View / visita)",
  "Verificar margem de erro do equipamento (5% ou 3 km/h — Port. INMETRO 056/2009)",
  "Conferir se o veículo da foto é o do cliente (placa/modelo/cor — clonagem?)",
  "Protocolar no prazo com COMPROVANTE DE PROTOCOLO (guardar nº)",
];

export default function GuiaTransito() {
  const [marcados, setMarcados] = useState<Record<number, boolean>>({});
  useEffect(() => {
    try {
      setMarcados(
        JSON.parse(localStorage.getItem("guia_transito_chk") || "{}"),
      );
    } catch {}
  }, []);
  const toggle = (i: number) => {
    const novo = { ...marcados, [i]: !marcados[i] };
    setMarcados(novo);
    localStorage.setItem("guia_transito_chk", JSON.stringify(novo));
  };
  const feitos = Object.values(marcados).filter(Boolean).length;

  return (
    <div className="card p-4 mb-4 border-l-4 border-blue-500">
      <div className="flex items-center gap-2 mb-1">
        <BookOpen size={16} className="text-bronze" />
        <h2 className="font-serif font-semibold text-navy text-sm">
          Guia Operacional de Multas de Trânsito
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Referência interna (prazos, infrações, defesas, recursos, pontos,
        prescrição). O mesmo acervo alimenta o Assistente IA e o Motor de Teses.
        Trânsito é guiado por prazos — calcule-os assim que receber o caso.
      </p>

      <div className="space-y-2">
        <Sec icon={Clock} titulo="Tabela mestra de prazos (crítico)" aberto>
          <Tab
            head={["Gatilho", "Prazo", "Ato", "Base"]}
            rows={[
              [
                "Data da NIA",
                "30 dias",
                "Indicação do condutor",
                "CTB 257 §8º",
              ],
              ["Data da NIA", "30 dias", "Defesa prévia", "CTB 281 §único"],
              [
                "Data da NIP",
                "30 dias",
                "Pagamento c/ 20% desconto",
                "CTB 284",
              ],
              ["Data da NIP", "30 dias", "Recurso JARI (1ª inst.)", "CTB 285"],
              [
                "Decisão JARI",
                "30 dias",
                "Recurso CETRAN/CONTRAN",
                "CTB 288 §1º",
              ],
              [
                "Decisão CETRAN",
                "120 dias",
                "Mandado de segurança",
                "Lei 12.016/09 art. 23",
              ],
              [
                "Data da infração",
                "12 meses",
                "Expiração dos pontos",
                "CTB 261",
              ],
              ["Data da infração", "5 anos", "Prescrição", "CTB 322"],
            ]}
          />
          <p className="text-amber-700">
            ⚠ Pagamento e recurso (ambos 30d da NIP) são SIMULTÂNEOS — pagar =
            desistência tácita do recurso (STJ). Dias corridos; vencimento em
            fim de semana/feriado prorroga ao dia útil.
          </p>
        </Sec>

        <Sec icon={Gauge} titulo="Infrações, natureza e pontuação">
          <Tab
            head={["Natureza", "Pontos", "Valor ~", "Exemplo"]}
            rows={[
              ["Leve", "3", "R$ 88", "Estacionar proibido comum"],
              ["Média", "4", "R$ 130", "Ultrapassagem pela direita"],
              ["Grave", "5", "R$ 195", "Avanço de sinal, sem cinto"],
              ["Gravíssima", "7", "variável", "Embriaguez, vel. >50%, racha"],
            ]}
          />
          <Tab
            head={["Infração", "CTB", "Fator/Pts"]}
            rows={[
              ["Velocidade até 20%", "218 I", "leve · 3"],
              ["Velocidade 20-50%", "218 II", "grave · 5"],
              ["Velocidade >50%", "218 III", "×3 · 7"],
              ["Celular ao volante", "252 V", "×5 · 7"],
              ["Avanço sinal vermelho", "208", "gravíssima · 7"],
              ["Embriaguez ≥0,3mg/L", "165", "×7 · 7 + CNH susp."],
              ["Dirigir sem CNH", "162 I", "×3 · 7 + apreensão"],
              ["Fuga de blitz", "165-A", "×10 · 7 + CNH susp."],
            ]}
          />
          <p className="text-slate-500">
            Valores aproximados — atualizar na portaria SENATRAN vigente.
          </p>
        </Sec>

        <Sec icon={FileWarning} titulo="Defesa prévia — teses (CTB 281 §único)">
          <p>
            <b>A) Nulidade formal do auto:</b> ausência de data/hora/local,
            agente, nº do equipamento+INMETRO; descrição incompatível com o
            dispositivo; placa/modelo/cor divergente; sem assinatura; agente sem
            competência. Base Res. CONTRAN 619/2016 art. 2º. Princípio pas de
            nullité sans grief.
          </p>
          <p>
            <b>B) Equipamento:</b> aferição vencida (pedir via LAI o certificado
            → nulidade); sem aprovação de modelo INMETRO; sem sinalização
            prévia; margem de erro (Port. INMETRO 056/2009: 5% ou 3 km/h — ex.:
            limite 60, medido 63, margem 3,15 → 59,85 → não configura).
          </p>
          <p>
            <b>C) Sinalização:</b> limite não sinalizado/ilegível; placa não
            visível; sinalização contraditória. CTB 88-97 e 178. Pedir via LAI
            registros de manutenção.
          </p>
          <p>
            <b>D) Placa clonada:</b> foto mostra veículo diferente. Provar com
            imagens, B.O. de clonagem, CRLV. STJ: proprietário não responde por
            veículo clonado.
          </p>
          <p>
            <b>E) Caso fortuito/força maior (CTB 280 §3º):</b> desvio de
            obstáculo, falha mecânica, emergência médica, parada para socorro
            (CTB 176). Prova contemporânea (prontuário, BO, laudo datado).
          </p>
        </Sec>

        <Sec icon={Scale} titulo="Recursos administrativos e judiciais">
          <p>
            <b>JARI (1ª inst.):</b> 30 dias da NIP (CTB 285); efeito suspensivo;
            gratuito; decide em 30 dias (prorrogável); silêncio = provido.
            Atacar os fundamentos da rejeição + juntar certidões do equipamento.
          </p>
          <p>
            <b>CETRAN (2ª inst.):</b> 30 dias da decisão JARI (CTB 288 §1º); MG
            p/ municipais/estaduais, CONTRAN p/ federais (PRF). Prazo fatal —
            última instância administrativa.
          </p>
          <p>
            <b>Mandado de segurança:</b> 120 dias do ato (Lei 12.016/09 art.
            23); TJMG. Usar p/ suspensão de CNH sem contraditório, pontos de
            infração anulada, multa prescrita. Liminar (art. 7º §3º) suspende o
            ato, sem depósito.
          </p>
          <p>
            <b>Ação anulatória:</b> via exaurida/vício insanável; 5 anos (Dec.
            20.910/32). Pedidos: nulidade + cancelar pontos + devolução
            (indébito CC 876/CDC 42/CTB 323) + tutela (CPC 300).
          </p>
        </Sec>

        <Sec icon={CreditCard} titulo="Pontos, CNH, frota e prescrição">
          <p>
            <b>Limites de suspensão (Lei 14.071/2020, 12 meses):</b> 40 pts (só
            leves/médias) · 30 pts (1-2 graves) · 20 pts (alguma gravíssima ou
            +2 graves). Conta a DATA DA INFRAÇÃO; pontos expiram em 12 meses;
            qualquer gravíssima reduz o limite a 20.
          </p>
          <p>
            <b>Suspensão:</b> direito ao contraditório — 30 dias de recurso à
            JARI antes de efetivar (CTB 261 §3º); 6 meses a 1 ano. Teses: pontos
            expirados, recursos pendentes, erro de contagem, infração geradora
            anulada.
          </p>
          <p>
            <b>Cassação (CTB 263):</b> reincidência, crime doloso c/ morte, 20
            pts em suspensão. Permanente (novo processo após 2 anos) — MS
            imediato.
          </p>
          <p>
            <b>Renovação (Lei 14.071):</b> 18-49 anos 10 anos · 50-69 5 anos ·
            70+ 3 anos. Multa não paga NÃO bloqueia renovação (STJ);
            suspensão/cassação bloqueiam.
          </p>
          <p>
            <b>Frota/PJ (CTB 257 §7º-8º):</b> 30 dias da NIA p/ indicar
            condutor; não indicando, multa no CNPJ mas SEM pontos. Indicado
            recebe nova NIA com defesa própria.
          </p>
          <p>
            <b>Prescrição (CTB 322):</b> 5 anos da infração; notificação válida
            interrompe; pode ser declarada de ofício. Execução fiscal: 5 anos
            (Lei 6.830/80). Não pagar multa prescrita sem verificar.
          </p>
        </Sec>

        <Sec
          icon={ListChecks}
          titulo={`Checklist do caso de trânsito (${feitos}/${CHECKLIST.length})`}
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
        Instrumento interno. Verificar atualização de resoluções CONTRAN,
        valores SENATRAN e tabela de pontos.
      </p>
    </div>
  );
}
