import { describe, expect, it } from "vitest";
import { formatObjectNameDisplay } from "./name";

describe("formatObjectNameDisplay", () => {
  it("returns em dash for empty value", () => {
    expect(formatObjectNameDisplay("")).toBe("—");
  });

  it("returns cleaned object name", () => {
    const value = "Мобильная установка 2 апреля 2026 г. Страница 5 из 200";
    expect(formatObjectNameDisplay(value)).toBe("Мобильная установка");
  });

  it("cuts service and address tails", () => {
    const value =
      "Дробильно-сортировочный комплекс ОАО \"Управление\" 220075, ул. Промышленная, 23, г. Минск (017) 344-55-22";
    expect(formatObjectNameDisplay(value)).toBe("Дробильно-сортировочный комплекс");
  });

  it("keeps compact object title from long comma stream", () => {
    const value =
      "Мобильный дробильный комплекс мультипроцессор МР 318, гидромолот SHD 150А, экскаватор Caterpillar 329, г. Заславль, ул. Советская, 133";
    expect(formatObjectNameDisplay(value)).toBe(
      "Мобильный дробильный комплекс мультипроцессор МР 318, гидромолот SHD 150А, экскаватор Caterpillar 329",
    );
  });

  it("removes waste type prefix from object field", () => {
    const value = "Бой бетонных изделий Мобильная установка (017) 344-55-22, г. Заславль";
    expect(formatObjectNameDisplay(value, "Бой бетонных изделий")).toBe("Мобильная установка");
  });

  it("removes generic waste intro even without waste_type_name", () => {
    const value = "Бой бетонных изделий Опытная установка по переработке строительных отходов";
    expect(formatObjectNameDisplay(value)).toBe("Опытная установка по переработке строительных отходов");
  });

  it("removes service header fragment in object field", () => {
    const value = "от других Бой бетонных изделий Дробильно-сортировочный комплекс";
    expect(formatObjectNameDisplay(value, "Бой бетонных изделий")).toBe("Дробильно-сортировочный комплекс");
  });

  it("removes 'принимает от других' prefix variant", () => {
    const value = "Принимает от других Бой бетонных изделий Мобильный комплекс по переработке минеральных отходов";
    expect(formatObjectNameDisplay(value, "Бой бетонных изделий")).toBe(
      "Мобильный комплекс по переработке минеральных отходов",
    );
  });

  it("cuts long legal tail after object title", () => {
    const value =
      "Стационарный дробильно-сортировочный комплекс Коммунальное унитарное предприятие по проектированию, ремонту и строительству дорог";
    expect(formatObjectNameDisplay(value)).toBe("Стационарный дробильно-сортировочный комплекс");
  });

  it("returns informative placeholder for dash-like value", () => {
    expect(formatObjectNameDisplay("—")).toBe("Не указан в реестре");
  });

  it("does not leave dangling preposition after cleanup", () => {
    const value = "Мобильный комплекс по";
    expect(formatObjectNameDisplay(value)).toBe("Мобильный комплекс");
  });
});
