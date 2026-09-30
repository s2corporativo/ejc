// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { officeBranding } from "../../config/officeBranding";
import { IdentidadeAssistente } from "./IdentidadeAssistente";

afterEach(cleanup);

describe("IdentidadeAssistente", () => {
  it("lê a origem do asset do branding, sem prop src", () => {
    render(<IdentidadeAssistente />);

    const img = screen.getByRole("img");
    expect(img.getAttribute("src")).toBe(officeBranding.logoPath);
    expect(officeBranding.logoPath).toBeTruthy();
  });

  it("descreve a marca com alt derivado do nome do escritório", () => {
    render(<IdentidadeAssistente />);

    const alt = screen.getByRole("img").getAttribute("alt") ?? "";
    expect(alt.length).toBeGreaterThan(0);
    expect(alt).toContain(officeBranding.officeName);
  });

  it("cai nas iniciais DT quando o asset falha", () => {
    render(<IdentidadeAssistente />);
    fireEvent.error(screen.getByRole("img"));

    const fallback = screen.getByRole("img");
    expect(fallback.tagName).toBe("SPAN");
    expect(fallback.textContent).toBe("DT");
  });

  it("mantém a marca acessível depois do fallback", () => {
    render(<IdentidadeAssistente />);
    fireEvent.error(screen.getByRole("img"));

    const alt = screen.getByRole("img").getAttribute("aria-label") ?? "";
    expect(alt).toContain(officeBranding.officeName);
  });
});
