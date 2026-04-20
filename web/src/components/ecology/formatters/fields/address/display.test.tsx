import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { formatAddressDisplay } from "./display";

describe("formatAddressDisplay", () => {
  it("returns fallback for empty address", () => {
    expect(formatAddressDisplay("")).toBe("—");
  });

  it("returns compact street address without postal code", () => {
    const out = renderToStaticMarkup(
      <>{formatAddressDisplay("223034, г. Заславль, ул. Советская, 133")}</>,
    );
    expect(out).toContain("г. Заславль, ул. Советская, 133");
    expect(out).not.toContain("223034");
  });

  it("removes owner and phone tails from address", () => {
    const out = renderToStaticMarkup(
      <>
        {formatAddressDisplay(
          '223034, г. Заславль, ул. Советская, 133, ООО "ПМК-42", (017) 443097',
        )}
      </>,
    );
    expect(out).toContain("г. Заславль, ул. Советская, 133");
    expect(out).not.toContain("ООО");
    expect(out).not.toContain("443097");
  });

  it("dedupes repeated locality segments and cuts duplicate tail", () => {
    const out = renderToStaticMarkup(
      <>
        {formatAddressDisplay(
          "223034, г. Заславль, г. Заславль, г. Заславль, ул. Советская, 133, г. 223034, ул. Советская, 133",
        )}
      </>,
    );
    expect(out).toContain("г. Заславль, ул. Советская, 133");
    expect(out).not.toContain("г. Заславль, г. Заславль");
  });
});
