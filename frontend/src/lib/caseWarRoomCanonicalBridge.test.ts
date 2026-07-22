import { describe, expect, it } from "vitest";

import { canonicalCaseWarRoomUrl } from "./caseWarRoomCanonicalBridge";

describe("canonicalCaseWarRoomUrl", () => {
  it("migra a simulação adversarial para o workspace canônico do caso", () => {
    expect(
      canonicalCaseWarRoomUrl(
        "/sala-de-guerra-v3/war-room/simular",
        "/casos/caso-123/sala-de-guerra",
      ),
    ).toBe("/cases/caso-123/sala-de-guerra/simular-contestacao");
  });

  it("migra o Visual Law para o workspace canônico do caso", () => {
    expect(
      canonicalCaseWarRoomUrl(
        "/sala-de-guerra-v3/visual-law/caso-123",
        "/casos/caso-123/sala-de-guerra",
      ),
    ).toBe("/cases/caso-123/sala-de-guerra/visual-law");
  });

  it("preserva a Sentinela global e chamadas sem contexto seguro", () => {
    expect(
      canonicalCaseWarRoomUrl(
        "/sala-de-guerra-v3/sentinela/auditoria",
        "/casos/caso-123/sala-de-guerra",
      ),
    ).toBe("/sala-de-guerra-v3/sentinela/auditoria");

    expect(
      canonicalCaseWarRoomUrl(
        "/sala-de-guerra-v3/war-room/simular",
        "/dashboard",
      ),
    ).toBe("/sala-de-guerra-v3/war-room/simular");
  });
});
