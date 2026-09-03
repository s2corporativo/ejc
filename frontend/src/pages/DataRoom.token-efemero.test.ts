import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const source = readFileSync(
  fileURLToPath(new URL("./DataRoom.tsx", import.meta.url)),
  "utf8",
);

describe("Data Room — token de link efêmero", () => {
  it("não presume que a listagem devolve o token secreto", () => {
    expect(source).not.toContain("lk.token");
    expect(source).toContain("URL não recuperável");
  });

  it("captura a URL somente da resposta de criação", () => {
    expect(source).toContain("data?.url_acesso");
    expect(source).toContain("setLinkRecemGerado({ url");
    expect(source).toContain("Por segurança, o token não fica armazenado em claro");
  });

  it("não persiste a capability URL em storage do navegador", () => {
    expect(source).not.toContain("localStorage");
    expect(source).not.toContain("sessionStorage");
  });
});
