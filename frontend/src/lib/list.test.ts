import { describe, it, expect } from "vitest";
import { asList } from "./list";

describe("asList", () => {
  it("aceita array cru", () => {
    expect(asList([1, 2, 3])).toEqual([1, 2, 3]);
    expect(asList([])).toEqual([]);
  });

  it("desempacota envelope { items: [] }", () => {
    expect(asList({ items: ["a", "b"] })).toEqual(["a", "b"]);
    expect(asList({ items: [] })).toEqual([]);
  });

  it("desempacota envelope { data: [] }", () => {
    expect(asList({ data: [{ id: "1" }] })).toEqual([{ id: "1" }]);
  });

  it("prioriza items sobre data quando ambos presentes", () => {
    expect(asList({ items: [1], data: [2, 3] })).toEqual([1]);
  });

  it("retorna [] para valores inesperados", () => {
    expect(asList(null)).toEqual([]);
    expect(asList(undefined)).toEqual([]);
    expect(asList("texto")).toEqual([]);
    expect(asList(42)).toEqual([]);
    expect(asList({ foo: "bar" })).toEqual([]);
    expect(asList({ items: "não-array" })).toEqual([]);
  });
});
