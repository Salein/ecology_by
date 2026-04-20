import { describe, expect, it } from "vitest";
import { formatWasteTypeDisplay } from "./type";

describe("formatWasteTypeDisplay", () => {
  it("returns em dash for empty value", () => {
    expect(formatWasteTypeDisplay("")).toBe("—");
  });

  it("cuts technical tails from waste type text", () => {
    const value =
      'Бой бетонных изделий Дробильно-сортировочный комплекс ОАО "ПМК-42" 220075, г. Минск, ул. Промышленная';
    expect(formatWasteTypeDisplay(value)).toBe("Бой бетонных изделий");
  });

  it("cuts equipment continuation after waste name", () => {
    const value =
      "Бой изделий из ячеистого бетона Пила промышленная для резки боя блоков из ячеистого бетона (";
    expect(formatWasteTypeDisplay(value)).toBe("Бой изделий из ячеистого бетона");
  });
});
