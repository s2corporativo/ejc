import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Clock3,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router";
import api from "../lib/api";
import { useAuth } from "../stores/auth";

type PrazoRadar = {
  id: string;
  data_prazo: string;
  data_intimacao?: string | null;
  dias_restantes?: number;
  confirmado?: boolean;
  ciencia_confirmada?: boolean;
};

type DiagnosticoSub = { nome: string; status: string; detalhe?: string };

const GESTORES = new Set(["superadmin", "admin", "socio"]);

// `GET /deadlines/` pagina: devolve no máximo `page_size` itens (teto 200) e a
// contagem real em `total`. Este radar pedia 100 e contava o TAMANHO DO ARRAY —
// com 300 prazos vencidos exibia "100 vencido(s)". É o mesmo defeito que esta
// correção veio consertar (um contador de prazos que mente para menos), só que
// aparecendo por volume em vez de por status. Paginamos até o fim; passando do
// teto, o número vira piso explícito ("100+") em vez de número errado.
//
// O contador de VENCIDOS não depende desse teto: o `total` da faixa `vencido`
// é a contagem do servidor e vem já na primeira resposta. Paginar existe para
// os outros quatro contadores, que dependem de campo de CADA item
// (dias_restantes, confirmado, ciencia_confirmada) e não têm agregação pronta.
const PAGE_SIZE = 200;
const MAX_PAGINAS = 5;

async function buscarPrazos(
  status: string,
): Promise<{ itens: PrazoRadar[]; total: number; completo: boolean }> {
  const pedir = (page: number) =>
    api.get("/deadlines/", { params: { status, page_size: PAGE_SIZE, page } });
  const lista = (r: { data?: { data?: unknown } }) =>
    Array.isArray(r.data?.data) ? (r.data.data as PrazoRadar[]) : [];

  const primeira = await pedir(1);
  const itens = lista(primeira);
  const total = Number(primeira.data?.total);

  // `total` ausente, nulo ou zerado não é prova de que veio tudo — `Number(null)`
  // é 0, e um 0 acompanhado de página cheia significa contagem faltando, não
  // lista vazia. Nesse caso só a página incompleta prova o fim.
  if (!Number.isFinite(total) || total <= 0) {
    return { itens, total: itens.length, completo: itens.length < PAGE_SIZE };
  }

  const paginas = Math.min(Math.ceil(total / PAGE_SIZE), MAX_PAGINAS);
  if (paginas > 1) {
    // `allSettled`: uma página que falha custa precisão, não a tira inteira.
    // Com `all`, buscar mais páginas aumentaria a chance de o radar sumir do
    // dashboard justamente para quem tem MAIS prazos. O que não veio entra no
    // "+", que é exatamente o que ele significa.
    const restantes = await Promise.allSettled(
      Array.from({ length: paginas - 1 }, (_, i) => pedir(i + 2)),
    );
    for (const r of restantes) {
      if (r.status === "fulfilled") itens.push(...lista(r.value));
    }
  }
  return { itens, total, completo: itens.length >= total };
}

export default function DeadlineRiskStrip() {
  const role = useAuth((state) => state.user?.role);
  const [prazos, setPrazos] = useState<PrazoRadar[]>([]);
  const [calendario, setCalendario] = useState<DiagnosticoSub | null>(null);
  const [erro, setErro] = useState(false);
  const [truncado, setTruncado] = useState(false);
  const [vencidosServidor, setVencidosServidor] = useState<number | null>(null);
  const [estourados, setEstourados] = useState(0);

  useEffect(() => {
    let ativo = true;
    const carregar = async () => {
      try {
        // `status` no backend é igualdade exata, e o job das 07:10
        // (`scheduler._marcar_prazos_vencidos`) move o prazo estourado de
        // "pendente" para "vencido". Buscar só "pendente" fazia este radar
        // contar ZERO vencidos por construção, todo dia depois das 07:10 —
        // justamente o número que ele existe para mostrar. As duas faixas
        // juntas são o conjunto de prazos EM ABERTO; concluído e cancelado
        // continuam de fora.
        const [pendentes, vencidos] = await Promise.all([
          buscarPrazos("pendente"),
          buscarPrazos("vencido"),
        ]);
        if (!ativo) return;
        const emAberto = [...pendentes.itens, ...vencidos.itens];
        setPrazos(emAberto);
        // Fallback local (só vale quando a agregação do servidor falha): conta
        // por DATA sobre as DUAS faixas. Contar só `pendentes` era o Achado 7
        // reaparecendo aqui dentro — depois do job das 07:10 o prazo estourado
        // deixa a faixa `pendente`, e este caminho exibiria "0 vencido(s)" com
        // os vencidos carregados na mão. `dias_restantes < 0` também exclui, de
        // graça, o reagendado que ficou com status `vencido` e data futura.
        setEstourados(
          emAberto.filter((p) => Number(p.dias_restantes) < 0).length,
        );
        setTruncado(!pendentes.completo || !vencidos.completo);
        setErro(false);
      } catch {
        if (ativo) setErro(true);
      }

      // Contagem de vencidos: agregação do servidor, não soma de página.
      // `GET /dashboard/` conta `data_prazo < hoje AND status NOT IN
      // ('concluido','cancelado')` — pela DATA, não pelo status. Isso resolve
      // dois defeitos de uma vez:
      //   1. teto de paginação: acima de 1.000 prazos em qualquer faixa, contar
      //      itens carregados subnotifica (era "1000+", piso e não contagem);
      //   2. prazo REAGENDADO para o futuro que continua com status `vencido` —
      //      `PATCH /deadlines/{id}` usa `exclude_unset`, então enviar só
      //      `data_prazo` (é o que `CentralAtividades` faz ao reagendar) preserva
      //      o status antigo. Contar por status exibiria como vencido um prazo
      //      futuro, e o dashboard — que conta por data — mostraria outro número.
      //      Dois painéis discordando é o defeito que este PR veio consertar.
      try {
        const dash = await api.get("/dashboard/");
        // `GET /dashboard/` NÃO falha quando um bloco seu falha: responde 200,
        // mantém o default `pv = 0` e nomeia o bloco em `degradado`. Aceitar
        // esse zero como contagem autoritativa faria uma falha transitória do
        // banco virar "0 vencido(s)" na tela — número errado com cara de
        // apurado, e justamente o número que este radar existe para não errar.
        // Sem o bloco de prazos, não há agregação: cai no fallback local.
        const degradado = dash.data?.degradado;
        const prazosDegradou =
          Array.isArray(degradado) && degradado.includes("prazos");
        const n = Number(dash.data?.prazos?.vencidos);
        if (ativo) {
          setVencidosServidor(!prazosDegradou && Number.isFinite(n) ? n : null);
        }
      } catch {
        // Sem a agregação, cai no cálculo local (com "+" quando truncado).
        if (ativo) setVencidosServidor(null);
      }

      if (role && GESTORES.has(role)) {
        try {
          const diag = await api.get("/diagnostico/central");
          const subs = Array.isArray(diag.data?.subsistemas)
            ? (diag.data.subsistemas as DiagnosticoSub[])
            : [];
          const item = subs.find(
            (s) => s.nome === "Calendário jurídico de prazos",
          );
          if (ativo) setCalendario(item ?? null);
        } catch {
          // O radar de prazos não depende da Central de Diagnóstico. Falha/flag
          // desabilitada apenas omite o sinal administrativo do calendário.
        }
      }
    };
    void carregar();
    return () => {
      ativo = false;
    };
  }, [role]);

  const risco = useMemo(() => {
    let ate48h = 0;
    let preliminares = 0;
    let cienciaPendente = 0;
    let revisados = 0;

    for (const p of prazos) {
      const dias = Number(p.dias_restantes);
      if (Number.isFinite(dias) && dias >= 0 && dias <= 2) ate48h += 1;
      if (p.confirmado === false) preliminares += 1;
      if (p.data_intimacao && !p.ciencia_confirmada) cienciaPendente += 1;
      if (p.confirmado && (!p.data_intimacao || p.ciencia_confirmada))
        revisados += 1;
    }

    return {
      // Preferimos SEMPRE a agregação do servidor; o cálculo local só existe
      // como degradação quando ela falha, e aí carrega o "+" de piso.
      vencidos: vencidosServidor,
      ate48h,
      preliminares,
      cienciaPendente,
      revisados,
    };
  }, [prazos, vencidosServidor]);

  if (erro) {
    return (
      <div className="mb-3 flex items-center justify-between rounded-2xl border border-amber-200 bg-amber-50/70 px-4 py-3 text-xs text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100">
        <span className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          Radar de prazos temporariamente indisponível.
        </span>
        <Link
          to="/prazos"
          className="font-semibold underline underline-offset-2"
        >
          Abrir prazos
        </Link>
      </div>
    );
  }

  const calendarioAlerta = calendario && calendario.status !== "ok";
  // Os cinco contadores saem da MESMA lista; se ela veio truncada, todos são
  // piso, não total. Melhor "200+ vencido(s)" do que "200" quando são 340.
  const piso = (v: number) => `${v}${truncado ? "+" : ""}`;

  return (
    <section className="mb-3 rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm backdrop-blur dark:border-white/10 dark:bg-slate-950/55">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ejc-primary text-ejc-gold-bright dark:bg-white/10">
            <ShieldAlert className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <strong className="text-xs font-semibold text-slate-900 dark:text-white">
              Radar de risco de prazos
            </strong>
            <p className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400">
              Contagens operacionais; confirmação jurídica continua humana.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold">
          <RiskChip
            icon={AlertTriangle}
            label={
              risco.vencidos !== null
                ? `${risco.vencidos} vencido(s)`
                : `${piso(estourados)} vencido(s)`
            }
            danger={(risco.vencidos ?? estourados) > 0}
          />
          <RiskChip
            icon={Clock3}
            label={`${piso(risco.ate48h)} até 48h`}
            warning={risco.ate48h > 0}
          />
          <RiskChip
            icon={CalendarClock}
            label={`${piso(risco.preliminares)} preliminar(es)`}
            warning={risco.preliminares > 0}
          />
          <RiskChip
            icon={AlertTriangle}
            label={`${piso(risco.cienciaPendente)} ciência pendente`}
            warning={risco.cienciaPendente > 0}
          />
          <RiskChip
            icon={CheckCircle2}
            label={`${piso(risco.revisados)} revisado(s)`}
            ok
          />
          {calendarioAlerta && (
            <RiskChip
              icon={ShieldAlert}
              label="calendário não validado"
              danger={calendario.status === "erro"}
              warning={calendario.status !== "erro"}
            />
          )}
        </div>

        <Link
          to="/prazos"
          className="inline-flex shrink-0 items-center gap-1 text-[10px] font-semibold text-slate-700 hover:text-amber-800 dark:text-slate-200 dark:hover:text-amber-200"
        >
          Abrir prazos <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </section>
  );
}

function RiskChip({
  icon: Icon,
  label,
  danger = false,
  warning = false,
  ok = false,
}: {
  icon: LucideIcon;
  label: string;
  danger?: boolean;
  warning?: boolean;
  ok?: boolean;
}) {
  const cls = danger
    ? "border-red-200 bg-red-50 text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200"
    : warning
      ? "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200"
      : ok
        ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200"
        : "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 ${cls}`}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label}
    </span>
  );
}
