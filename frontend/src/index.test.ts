import { describe, expect, it } from "vitest";

import { formatServiceBanner } from "./index.js";

describe("formatServiceBanner", () => {
  it("formats name and version", () => {
    expect(formatServiceBanner({ name: "hello", version: "0.1.0" })).toBe(
      "Chartwright · hello v0.1.0",
    );
  });
});
