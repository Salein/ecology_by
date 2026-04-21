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

  it("cuts enterprise and equipment tail for polyethylene code", () => {
    const value =
      'Полиэтилен агломератор роторный OULI-150 Общество с дополнительной ответственностью "АлтехБел"';
    expect(formatWasteTypeDisplay(value)).toBe("Полиэтилен");
  });

  it("cuts biogas complex tail from grain waste type", () => {
    const value =
      'Отходы зерновые 3 категории Биогазовый комплекс в СПК "Агрокомбинат "Снов" Несвижского района Минской области';
    expect(formatWasteTypeDisplay(value)).toBe("Отходы зерновые 3 категории");
  });

  it("cuts reconstruction and owner tail", () => {
    const value =
      "Кукурузные обертки Реконструкция сооружения неустановленного назначения Общество с ограниченной ответственностью «Датком Столица»";
    expect(formatWasteTypeDisplay(value)).toBe("Кукурузные обертки");
  });

  it("cuts machine shredder tail", () => {
    const value =
      'Отходы зерновые 3 категории Машина рубильная Шредер Doppstadt DW3060K typ BioPower ООО "ВторИнвест"';
    expect(formatWasteTypeDisplay(value)).toBe("Отходы зерновые 3 категории");
  });
});
