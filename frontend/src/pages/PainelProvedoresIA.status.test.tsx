import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  STATUS_PROVEDOR,
  StatusBadge,
  rotuloStatusProvedor,
} from "./PainelProvedoresIA";

vi.mock("../lib/api", () => ({ default: { get: vi.fn() } }));
vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }));

// Vocabulário real emitido por routers/ia_governanca.py (_status_provedor).
const VOCABULARIO_BACKEND = [
  "nao_configurado",
  "sem_registro",
  "operacional",
  "degradado",
  "critico",
];

describe("Painel de Provedores — vocabulário de status (E3)", () => {
  it("cobre exatamente os cinco status do backend", () => {
    expect(Object.keys(STATUS_PROVEDOR).sort()).toEqual(
      [...VOCABULARIO_BACKEND].sort(),
    );
  });

  it("crítico é vermelho, degradado âmbar, operacional verde", () => {
    expect(STATUS_PROVEDOR.critico.classe).toMatch(/danger/);
    expect(STATUS_PROVEDOR.degradado.classe).toMatch(/warn/);
    expect(STATUS_PROVEDOR.operacional.classe).toMatch(/success/);
    expect(STATUS_PROVEDOR.nao_configurado.classe).toMatch(/slate/);
    expect(STATUS_PROVEDOR.sem_registro.classe).toMatch(/primary/);
  });

  it("rótulos em pt-BR e fallback legível para status desconhecido", () => {
    expect(rotuloStatusProvedor("critico")).toBe("Crítico");
    expect(rotuloStatusProvedor("nao_configurado")).toBe("Não configurado");
    expect(rotuloStatusProvedor("algo_novo")).toBe("algo novo");
  });

  it("badge renderiza a classe do status real (crítico nunca vira cinza)", () => {
    render(<StatusBadge status="critico" />);
    const badge = screen.getByText("Crítico");
    expect(badge.className).toMatch(/danger/);
    expect(badge.className).not.toMatch(/slate/);
  });
});
