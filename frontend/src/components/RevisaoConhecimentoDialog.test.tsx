// Revisão humana de documento da base de conhecimento — três achados da
// revisão automatizada do PR (03/09/2026):
//   1. aprovação era liberada sem NENHUM texto do documento na tela;
//   2. as `notas` iam no corpo mas o backend não as declarava (descartadas);
//   3. decisão e confiança eram duas requisições — falhar a segunda deixava o
//      documento aprovado sem nível de confiança.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ERRO_NOTAS_OBRIGATORIAS,
  ERRO_SEM_TEXTO_PARA_APROVAR,
  RevisaoConhecimentoDialog,
  registrarRevisaoConhecimento,
} from "./RevisaoConhecimentoDialog";
import api from "../lib/api";

vi.mock("../lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
};

const DOC_COM_TEXTO = {
  id: "d1",
  titulo: "Acórdão TJMG sobre vício do produto",
  extra: { ementa: "Vício do produto. Responsabilidade solidária." },
};

const DOC_SEM_TEXTO = { id: "d2", titulo: "PDF digitalizado sem OCR" };

// Caso REAL da maioria do acervo: o texto vive em KnowledgeChunk.conteudo e
// chega pela prévia, não por `extra`.
const DOC_SO_COM_PREVIA = {
  id: "d4",
  titulo: "Lei 8.078/1990 — CDC",
  previa_texto: "Art. 42. Na cobrança de débitos, o consumidor inadimplente "
    + "não será exposto a ridículo, nem submetido a constrangimento.",
  previa_truncada: true,
};

function abrir(props: Partial<Parameters<typeof RevisaoConhecimentoDialog>[0]> = {}) {
  return render(
    <RevisaoConhecimentoDialog
      docId="d1"
      decisao="aprovar"
      onFechar={() => {}}
      onConcluido={() => {}}
      {...props}
    />,
  );
}

const botao = (nome: RegExp) =>
  screen.getByRole("button", { name: nome }) as HTMLButtonElement;
const notas = () => screen.getByLabelText("Notas da revisão") as HTMLTextAreaElement;

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.post.mockResolvedValue({ data: { detail: "ok" } });
});

describe("aprovação sem texto visível", () => {
  it("bloqueia até o revisor declarar que conferiu o original", async () => {
    mockApi.get.mockResolvedValue({ data: DOC_SEM_TEXTO });
    abrir({ docId: "d2" });
    await screen.findByText("PDF digitalizado sem OCR");

    fireEvent.change(notas(), { target: { value: "documento antigo do acervo" } });
    expect(botao(/Aprovar/).disabled).toBe(true);

    fireEvent.click(screen.getByRole("checkbox"));
    expect(botao(/Aprovar/).disabled).toBe(false);
    fireEvent.click(botao(/Aprovar/));
    await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(1));
  });

  it("REJEITAR não exige a declaração — recusar às cegas não contamina a IA", async () => {
    mockApi.get.mockResolvedValue({ data: DOC_SEM_TEXTO });
    abrir({ docId: "d2", decisao: "rejeitar" });
    await screen.findByText("PDF digitalizado sem OCR");

    expect(screen.queryByRole("checkbox")).toBeNull();
    fireEvent.change(notas(), { target: { value: "fonte não confiável" } });
    fireEvent.click(botao(/Rejeitar/));
    await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(1));
  });

  it("prévia do texto indexado dispensa a declaração e fica visível", async () => {
    mockApi.get.mockResolvedValue({ data: DOC_SO_COM_PREVIA });
    abrir({ docId: "d4" });
    await screen.findByText("Lei 8.078/1990 — CDC");

    expect(screen.getByText(/consumidor inadimplente/)).toBeTruthy();
    expect(screen.getByText(/Prévia truncada/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(botao(/Aprovar/).disabled).toBe(false);
  });

  it("documento COM ementa não pede declaração extra", async () => {
    mockApi.get.mockResolvedValue({ data: DOC_COM_TEXTO });
    abrir();
    await screen.findByText("Acórdão TJMG sobre vício do produto");
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(botao(/Aprovar/).disabled).toBe(false);
  });
});

describe("notas obrigatórias", () => {
  it("recusa o envio com notas em branco e explica o motivo", async () => {
    mockApi.get.mockResolvedValue({ data: DOC_COM_TEXTO });
    abrir();
    await screen.findByText("Acórdão TJMG sobre vício do produto");

    fireEvent.click(botao(/Aprovar/));
    expect(screen.getByRole("alert").textContent).toContain(
      ERRO_NOTAS_OBRIGATORIAS,
    );
    expect(mockApi.post).not.toHaveBeenCalled();
  });

  it("limpa notas e erro ao trocar de documento", async () => {
    mockApi.get.mockResolvedValue({ data: DOC_COM_TEXTO });
    const { rerender } = abrir();
    await screen.findByText("Acórdão TJMG sobre vício do produto");
    fireEvent.change(notas(), { target: { value: "conferido no TJMG" } });

    mockApi.get.mockResolvedValue({ data: { ...DOC_COM_TEXTO, id: "d3" } });
    rerender(
      <RevisaoConhecimentoDialog
        docId="d3"
        decisao="aprovar"
        onFechar={() => {}}
        onConcluido={() => {}}
      />,
    );
    await waitFor(() => expect(notas().value).toBe(""));
  });
});

describe("registrarRevisaoConhecimento", () => {
  it("envia decisão, notas e confiança numa ÚNICA requisição", async () => {
    await registrarRevisaoConhecimento({
      docId: "d1",
      decisao: "aprovar",
      notas: "ementa conferida na fonte oficial",
      confidenceLevel: "alta",
    });

    expect(mockApi.patch).not.toHaveBeenCalled();
    expect(mockApi.post).toHaveBeenCalledTimes(1);
    expect(mockApi.post).toHaveBeenCalledWith("/rag/governanca/docs/d1/revisar", {
      aprovado: true,
      notas: "ementa conferida na fonte oficial",
      confidence_level: "alta",
    });
  });

  it("omite confidence_level quando o chamador não o informa", async () => {
    await registrarRevisaoConhecimento({
      docId: "d1",
      decisao: "rejeitar",
      notas: "superado por súmula posterior",
    });
    expect(mockApi.post).toHaveBeenCalledWith("/rag/governanca/docs/d1/revisar", {
      aprovado: false,
      notas: "superado por súmula posterior",
    });
  });
});

it("a mensagem do bloqueio de aprovação existe e é específica", () => {
  expect(ERRO_SEM_TEXTO_PARA_APROVAR).toMatch(/conferiu o original/);
});
