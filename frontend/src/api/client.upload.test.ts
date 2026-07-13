import { beforeEach, describe, expect, it } from "vitest";
import { http } from "./client";
import { documentApi } from "./services";

// Diagnostic: capture the FINAL outgoing request (after axios transformRequest)
// to see exactly what Content-Type a FormData upload actually carries.
describe("outgoing upload request", () => {
  let captured: any;
  beforeEach(() => {
    localStorage.setItem("cb_access_token", "tok");
    http.defaults.adapter = async (config: any) => {
      captured = config;
      return {
        data: { success: true, data: { id: "1", upload_status: "processing" } },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      };
    };
  });

  const ctOf = (c: any) =>
    String(c.headers?.getContentType?.() ?? c.headers?.["Content-Type"] ?? c.headers?.["content-type"] ?? "");

  it("does NOT send application/json for a FormData upload", async () => {
    const file = new File(["hello world"], "a.txt", { type: "text/plain" });
    await documentApi.upload("kb1", file);
    expect(ctOf(captured)).not.toContain("application/json");
  });

  it("sends the FormData body (not a stringified object)", async () => {
    const file = new File(["hello world"], "a.txt", { type: "text/plain" });
    await documentApi.upload("kb1", file);
    expect(captured.data instanceof FormData).toBe(true);
  });

  it("still sends application/json for JSON posts", async () => {
    await http.post("/api/v1/x", { a: 1 });
    expect(ctOf(captured)).toContain("application/json");
  });
});
