// @vitest-environment jsdom
// Regressão da auditoria funcional de 22/08/2026 (Issue #1237), encontrada na
// passagem pela interface renderizada: o dashboard exibia, lado a lado,
// "0 vencido(s)" neste radar e "3 prazos vencidos" no card de Prioridades.
//
// Causa: `status` no backend é igualdade exata, e o job das 07:10
// (`scheduler._marcar_prazos_vencidos`) move o prazo estourado de "pendente"
// para "vencido". Buscando só "pendente", o radar nunca recebia um prazo
// vencido — contava zero por construção, todo dia depois das 07:10. É o número
// que este componente existe para mostrar.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";

const get = vi.fn();
vi.mock("../lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a) },
}));
vi.mock("../stores/auth", () => ({
  useAuth: (sel: (s: unknown) => unknown) =>
    sel({ user: { role: "advogado" } }),
}));

import DeadlineRiskStrip from "./DeadlineRiskStrip";

const VENCIDO = {
  id: "v1",
  data_prazo: "2026-05-29",
  data_intimacao: "2026-05-24",
  dias_restantes: -85,
  confirmado: true,
  ciencia_confirmada: true,
};
const PENDENTE = {
  id: "p1",
  data_prazo: "2026-12-01",
  dias_restantes: 40,
  confirmado: true,
  ciencia_confirmada: true,
};

/** Imita a agregação real de `GET /dashboard/`: conta por DATA
 *  (`data_prazo < hoje AND status NOT IN ('concluido','cancelado')`), o que
 *  atravessa as duas faixas. Um falso servidor que contasse só a faixa
 *  `vencido` estaria testando uma regra que o backend não tem. */
function contarPorData(porStatus: Record<string, unknown[]>): number {
  return Object.values(porStatus)
    .flat()
    .filter(
      (p) => Number((p as { dias_restantes?: number }).dias_restantes) < 0,
    ).length;
}

function responder(
  porStatus: Record<string, unknown[]>,
  vencidosServidor?: number | null,
) {
  get.mockImplementation(
    (url: string, cfg?: { params?: { status?: string } }) => {
      if (url === "/dashboard/") {
        // `null` simula a agregação indisponível, para exercitar a degradação.
        if (vencidosServidor === null)
          return Promise.reject(new Error("dashboard fora do ar"));
        const n = vencidosServidor ?? contarPorData(porStatus);
        return Promise.resolve({ data: { prazos: { vencidos: n } } });
      }
      if (url !== "/deadlines/")
        return Promise.reject(new Error("rota inesperada"));
      return Promise.resolve({
        data: { data: porStatus[cfg?.params?.status ?? ""] ?? [] },
      });
    },
  );
}

describe("DeadlineRiskStrip — prazo vencido não pode sumir do radar", () => {
  afterEach(() => {
    cleanup();
    get.mockReset();
  });

  it("conta o prazo que o job das 07:10 marcou como 'vencido'", async () => {
    responder({ pendente: [PENDENTE], vencido: [VENCIDO] });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    // Antes da correção o componente pedia só `status=pendente` e este texto
    // seria "0 vencido(s)" — com o prazo estourado presente no banco.
    await waitFor(() => expect(screen.getByText("1 vencido(s)")).toBeTruthy());
  });

  it("busca as duas faixas em aberto, pendente e vencido", async () => {
    responder({ pendente: [], vencido: [] });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(get.mock.calls.filter((c) => c[0] === "/deadlines/")).toHaveLength(
        2,
      ),
    );
    const status = get.mock.calls
      .filter((c) => c[0] === "/deadlines/")
      .map((c) => (c[1] as { params?: { status?: string } })?.params?.status)
      .sort();
    expect(status).toEqual(["pendente", "vencido"]);
  });

  it("sem prazo estourado, o radar segue mostrando zero", async () => {
    responder({ pendente: [PENDENTE], vencido: [] });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("0 vencido(s)")).toBeTruthy());
  });
});

// ── Volume: a contagem não pode parar na primeira página ────────────────────
// Achado P1 da revisão do Codex em 2026-08-22 (PR #1238). Buscar uma página e
// contar `data.length` faz o radar exibir "100 vencido(s)" onde há 300 — o
// mesmo defeito que ele veio consertar (contador de prazo que mente para
// menos), agora por volume em vez de por status.

/** Servidor falso que pagina de verdade: respeita page/page_size e devolve `total`. */
function responderPaginado(
  porStatus: Record<string, unknown[]>,
  vencidosServidor?: number | null,
) {
  get.mockImplementation(
    (
      url: string,
      cfg?: { params?: { status?: string; page?: number; page_size?: number } },
    ) => {
      if (url === "/dashboard/") {
        if (vencidosServidor === null)
          return Promise.reject(new Error("dashboard fora do ar"));
        const n = vencidosServidor ?? contarPorData(porStatus);
        return Promise.resolve({ data: { prazos: { vencidos: n } } });
      }
      if (url !== "/deadlines/")
        return Promise.reject(new Error("rota inesperada"));
      const todos = porStatus[cfg?.params?.status ?? ""] ?? [];
      const size = cfg?.params?.page_size ?? 50;
      const page = cfg?.params?.page ?? 1;
      return Promise.resolve({
        data: {
          data: todos.slice((page - 1) * size, page * size),
          total: todos.length,
          page,
          page_size: size,
        },
      });
    },
  );
}

const vencidos = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    id: `v${i}`,
    data_prazo: "2026-05-29",
    dias_restantes: -1,
    confirmado: true,
    ciencia_confirmada: true,
  }));

describe("DeadlineRiskStrip — contagem sob volume", () => {
  afterEach(() => {
    cleanup();
    get.mockReset();
  });

  it("conta os 340 vencidos, não só a primeira página", async () => {
    responderPaginado({ pendente: [], vencido: vencidos(340) });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    // Antes da correção: "100 vencido(s)". Com página de 200 e sem paginar:
    // "200 vencido(s)". Só paginando até o fim dá 340.
    await waitFor(() =>
      expect(screen.getByText("340 vencido(s)")).toBeTruthy(),
    );
  });

  it("acima do teto de páginas, ainda conta os 3.000 vencidos", async () => {
    responderPaginado({ pendente: [], vencido: vencidos(3000) });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    // 2ª revisão do Codex: paginar até um TETO ainda subnotifica acima dele —
    // "1000+" era piso, não contagem. O `total` da faixa `vencido` vem exato na
    // primeira resposta; usá-lo tira este contador do teto de vez.
    await waitFor(() =>
      expect(screen.getByText("3000 vencido(s)")).toBeTruthy(),
    );
    expect(screen.queryByText("1000+ vencido(s)")).toBeNull();
  });

  it("soma o pendente já estourado que o job das 07:10 ainda não virou", async () => {
    const estourado = {
      id: "p9",
      data_prazo: "2026-08-21",
      dias_restantes: -1,
      confirmado: true,
      ciencia_confirmada: true,
    };
    responderPaginado({
      pendente: [estourado, PENDENTE],
      vencido: vencidos(4),
    });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    // 4 na faixa `vencido` + 1 pendente com dias_restantes < 0. Contar só o
    // `total` do servidor perderia a janela entre a virada do dia e o job.
    await waitFor(() => expect(screen.getByText("5 vencido(s)")).toBeTruthy());
  });

  it("não conta duas vezes o item que está na faixa vencido", async () => {
    responderPaginado({ pendente: [], vencido: vencidos(3) });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    // Os itens da faixa `vencido` têm dias_restantes < 0 e já estão no `total`.
    // Se o contador de estourados varresse a lista MERGED, daria 6.
    await waitFor(() => expect(screen.getByText("3 vencido(s)")).toBeTruthy());
  });

  it("cabendo tudo numa página, não aparece o '+'", async () => {
    responderPaginado({ pendente: [], vencido: vencidos(7) });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("7 vencido(s)")).toBeTruthy());
    expect(screen.queryByText("7+ vencido(s)")).toBeNull();
  });
});

// ── Contagem vem do servidor, não da soma de páginas ────────────────────────
// 3ª revisão do Codex (PR #1238). Usar o `total` da faixa `vencido` resolveu o
// teto para ELA, mas deixou dois furos: pendentes já estourados continuavam
// limitados às páginas carregadas, e contar por STATUS exibe como vencido um
// prazo reagendado para o futuro que manteve `status='vencido'` — `PATCH
// /deadlines/{id}` usa `exclude_unset`, e a Central envia só `data_prazo`.
//
// `GET /dashboard/` conta por DATA e atravessa as duas faixas: resolve os dois.

describe("DeadlineRiskStrip — contagem autoritativa de vencidos", () => {
  afterEach(() => {
    cleanup();
    get.mockReset();
  });

  it("usa a agregação do servidor acima de qualquer volume", async () => {
    responderPaginado({ pendente: [], vencido: vencidos(3000) }, 3000);
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText("3000 vencido(s)")).toBeTruthy(),
    );
  });

  it("conta pendentes estourados acima do teto de páginas", async () => {
    // 1.200 pendentes com dias_restantes < 0 (job das 07:10 atrasado). O teto
    // de 5 páginas carrega 1.000; contar itens diria "1000+".
    responderPaginado({ pendente: vencidos(1200), vencido: [] });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText("1200 vencido(s)")).toBeTruthy(),
    );
    expect(screen.queryByText("1000+ vencido(s)")).toBeNull();
  });

  it("prazo reagendado para o futuro não conta como vencido", async () => {
    // Ficou com status `vencido` mas dias_restantes > 0. O servidor conta por
    // data e não o inclui; contar por status exibiria 1.
    const reagendado = {
      id: "r1",
      data_prazo: "2026-12-01",
      dias_restantes: 101,
      confirmado: true,
      ciencia_confirmada: true,
    };
    responderPaginado({ pendente: [], vencido: [reagendado] });
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("0 vencido(s)")).toBeTruthy());
  });

  it("sem a agregação, degrada para o cálculo local com piso explícito", async () => {
    responderPaginado({ pendente: vencidos(1200), vencido: [] }, null);
    render(
      <MemoryRouter>
        <DeadlineRiskStrip />
      </MemoryRouter>,
    );
    // `/dashboard/` fora do ar: o radar não some nem mente — mostra piso.
    await waitFor(() =>
      expect(screen.getByText("1000+ vencido(s)")).toBeTruthy(),
    );
  });
});
