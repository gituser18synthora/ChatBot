import { describe, expect, it } from "vitest";
import { formatBytes, formatCurrency, initials, titleCase } from "./utils";

describe("formatters", () => {
  it("formats currency", () => {
    expect(formatCurrency(1.5)).toBe("$1.50");
    expect(formatCurrency(0)).toBe("$0.00");
  });
  it("formats bytes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
  });
  it("title-cases actions", () => {
    expect(titleCase("document_uploaded")).toBe("Document Uploaded");
  });
  it("computes initials", () => {
    expect(initials("Jane Doe")).toBe("JD");
    expect(initials("root")).toBe("R");
  });
});
