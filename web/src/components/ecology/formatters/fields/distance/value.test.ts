import { describe, expect, it } from "vitest";
import { distanceIsMissing, formatDistance, formatSpread } from "./value";

describe("distance formatters", () => {
  it("formats numeric values", () => {
    expect(formatDistance(25.4)).toBe("~25 км");
    expect(formatSpread(4.2)).toBe("±4 км");
  });

  it("handles missing values", () => {
    expect(formatDistance(null)).toBe("—");
    expect(formatSpread(undefined)).toBe("");
    expect(distanceIsMissing(undefined)).toBe(true);
  });
});
