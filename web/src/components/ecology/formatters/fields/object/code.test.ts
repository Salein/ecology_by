import { describe, expect, it } from "vitest";
import { formatObjectCode } from "./code";

describe("formatObjectCode", () => {
  it("returns em dash for nullish values", () => {
    expect(formatObjectCode(null)).toBe("—");
    expect(formatObjectCode(undefined)).toBe("—");
  });

  it("returns trimmed value for valid code", () => {
    expect(formatObjectCode(" 3679 ")).toBe("3679");
    expect(formatObjectCode(2765)).toBe("2765");
  });

  it("extracts numeric id from noisy input", () => {
    expect(formatObjectCode("id= 3551 / Объект")).toBe("3551");
    expect(formatObjectCode("без кода")).toBe("—");
  });
});
