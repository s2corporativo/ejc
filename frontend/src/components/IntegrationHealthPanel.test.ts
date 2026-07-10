import { describe, expect, it } from "vitest";
import {
  groupIntegrationItems,
  type IntegrationItem,
} from "./IntegrationHealthPanel";

const items: IntegrationItem[] = [
  {
    key: "ai",
    label: "IA",
    group: "Inteligência",
    enabled: true,
    configured: true,
    status: "ready",
    detail: "ok",
  },
  {
    key: "email",
    label: "E-mail",
    group: "Comunicação",
    enabled: true,
    configured: false,
    status: "attention",
    detail: "incompleta",
  },
  {
    key: "push",
    label: "Push",
    group: "Comunicação",
    enabled: false,
    configured: false,
    status: "disabled",
    detail: "desabilitada",
  },
];

describe("IntegrationHealthPanel", () => {
  it("agrupa integrações sem perder a ordem", () => {
    const groups = groupIntegrationItems(items);

    expect(groups.map(([group]) => group)).toEqual([
      "Inteligência",
      "Comunicação",
    ]);
    expect(groups[1][1].map((item) => item.key)).toEqual(["email", "push"]);
  });
});
