import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// `import.meta.url` não é `file:` no ambiente jsdom do vitest — o teste original
// (#1491) quebrava na carga com "The URL must be of scheme file". Mesmo padrão
// dos demais testes de contrato que leem a fonte da tela.
const source = readFileSync(join(__dirname, "DataRoom.tsx"), "utf8");

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
