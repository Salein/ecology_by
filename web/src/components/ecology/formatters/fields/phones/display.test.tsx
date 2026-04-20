import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { formatPhonesDisplay } from "./display";

describe("formatPhonesDisplay", () => {
  it("returns fallback for empty phones", () => {
    expect(formatPhonesDisplay("")).toBe("Не указан в реестре");
  });

  it("renders valid phone lines and drops invalid chunks", () => {
    const out = renderToStaticMarkup(
      <>
        {formatPhonesDisplay("(017) 344-55-22; +375 (17) 344-30-97; мусор")}
      </>,
    );
    expect(out).toContain("+375 (17) 344-55-22");
    expect(out).toContain("344");
    expect(out).not.toContain("мусор");
  });
});
