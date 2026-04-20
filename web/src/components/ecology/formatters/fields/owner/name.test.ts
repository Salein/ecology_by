import { describe, expect, it } from "vitest";
import { formatOwnerDisplay } from "./name";

describe("formatOwnerDisplay", () => {
  it("returns fallback for empty owner", () => {
    expect(formatOwnerDisplay("")).toBe("—");
  });

  it("removes page footer artifact", () => {
    const owner = 'ОАО "ПМК-42" 2 апреля 2026 г. Страница 10 из 250';
    expect(formatOwnerDisplay(owner)).toBe('ОАО "ПМК-42"');
  });

  it("cuts service tail after legal name", () => {
    const owner =
      'ООО "ВторИнвест" Использует собственные Принимает от других в соответствии с законодательством';
    expect(formatOwnerDisplay(owner)).toBe('ООО "ВторИнвест"');
  });

  it("falls back to legal name found in object text", () => {
    const object = 'Мобильная установка ОАО "ПМК-42", г. Заславль';
    expect(formatOwnerDisplay("", object, "")).toBe('ОАО "ПМК-42"');
  });

  it("does not keep generic owner fragment", () => {
    expect(formatOwnerDisplay("Управление")).toBe("—");
  });

  it("keeps legal chunk with digits and hyphen", () => {
    expect(formatOwnerDisplay('ОАО ПМК-42 трест')).toBe("ОАО ПМК-42 трест");
  });

  it("supports additional legal forms like KUP", () => {
    expect(formatOwnerDisplay('КУП "Горремавтодор"')).toBe('КУП "Горремавтодор"');
  });

  it("does not truncate long legal owner name", () => {
    const owner = 'ОАО "Дорожно-строительный трест №4 г. Брест"';
    expect(formatOwnerDisplay(owner)).toBe('ОАО "Дорожно-строительный трест №4 г. Брест"');
  });

  it("normalizes common typo in filial word", () => {
    const owner = 'филила ОАО "Барановичский комбинат ЖБК"';
    expect(formatOwnerDisplay(owner)).toBe('филиал ОАО "Барановичский комбинат ЖБК"');
  });

  it("uses organization hint from object when legal form missing", () => {
    const object = "Дробильно-сортировочный комплекс, дорожно-строительный трест Западный";
    expect(formatOwnerDisplay("", object, "")).toBe("дорожно-строительный трест Западный");
  });
});
