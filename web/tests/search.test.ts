import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchConsumerPage, parseConsumerPage, parseSearchQuery, SearchInputError, SearchUpstreamError, upstreamUrl } from "../lib/search";

const upstreamCard = {
  job_key: "job-1",
  title: "Product Designer",
  organization: "Acme",
  apply_url: "https://careers.acme.example/roles/1",
  first_seen: "2026-10-20T09:00:00Z",
  date_posted: "2026-10-19T09:00:00Z",
  location: "Bengaluru, India",
  remote: false,
  employment_type: ["FULL_TIME"],
  description_snippet: "Design useful tools."
};

afterEach(() => vi.restoreAllMocks());

describe("public search contract", () => {
  it("accepts only bounded search filters and an opaque cursor", () => {
    const query = parseSearchQuery(new URLSearchParams("q=+product++designer+&country=in&remote=only&cursor=abc_123"));
    expect(query).toEqual({ q: "product designer", country: "IN", remote: "only", cursor: "abc_123" });
    expect(upstreamUrl(query).toString()).toBe("https://praxyjobs.com/v1/internal/consumer/jobs/search?q=product+designer&country=IN&remote=only&cursor=abc_123&limit=24");
    expect(() => parseSearchQuery(new URLSearchParams("q=one&q=two"))).toThrow(SearchInputError);
    expect(() => parseSearchQuery(new URLSearchParams(`q=${"x".repeat(121)}`))).toThrow(SearchInputError);
    expect(() => parseSearchQuery(new URLSearchParams("remote=sometimes"))).toThrow(SearchInputError);
    expect(() => parseSearchQuery(new URLSearchParams("cursor=../../secrets"))).toThrow(SearchInputError);
  });

  it("maps only public card fields, preserving the original HTTPS apply link", () => {
    const result = parseConsumerPage({ schema_version: "praxy-consumer-jobs-v1", results: [upstreamCard], next_cursor: "next" });
    expect(result.jobs).toEqual([{ jobKey: "job-1", title: "Product Designer", organization: "Acme", applyUrl: "https://careers.acme.example/roles/1", sourceHost: "careers.acme.example", firstSeen: "2026-10-20T09:00:00Z", datePosted: "2026-10-19T09:00:00Z", location: "Bengaluru, India", workplace: null, remote: false, employmentType: ["FULL_TIME"], descriptionSnippet: "Design useful tools." }]);
    expect(result.nextCursor).toBe("next");
    expect(JSON.stringify(result)).not.toContain("company_logo_url");
  });

  it("rejects a non-HTTPS apply link or a changed upstream schema", () => {
    expect(() => parseConsumerPage({ schema_version: "praxy-consumer-jobs-v1", results: [{ ...upstreamCard, apply_url: "javascript:alert(1)" }] })).toThrow(SearchUpstreamError);
    expect(() => parseConsumerPage({ schema_version: "praxy-consumer-jobs-v1", results: [{ ...upstreamCard, apply_url: "https://127.0.0.1/private" }] })).toThrow(SearchUpstreamError);
    expect(() => parseConsumerPage({ schema_version: "praxy-consumer-jobs-v1", results: [{ ...upstreamCard, apply_url: "https://intranet.internal/role" }] })).toThrow(SearchUpstreamError);
    expect(() => parseConsumerPage({ schema_version: "other", results: [upstreamCard] })).toThrow(SearchUpstreamError);
  });

  it("never forwards an upstream error body or accepts an upstream redirect", async () => {
    const fetcher = vi.fn(async () => new Response("secret backend text", { status: 403 }));
    const query = parseSearchQuery(new URLSearchParams("q=designer"));
    await expect(fetchConsumerPage(query, "test-key", fetcher as typeof fetch)).rejects.toMatchObject({ status: 403 });
    expect(fetcher.mock.calls.length).toBe(1);
    const init = (fetcher.mock.calls as unknown[][])[0][1] as RequestInit;
    expect(init.headers).toMatchObject({ "X-API-Key": "test-key" });
    expect(init.redirect).toBe("error");
    expect(init.cache).toBe("no-store");
  });

  it("rejects oversized upstream JSON before parsing", async () => {
    const fetcher = vi.fn(async () => new Response("x".repeat(1_000_001), { status: 200 }));
    await expect(fetchConsumerPage(parseSearchQuery(new URLSearchParams()), "test-key", fetcher as typeof fetch)).rejects.toMatchObject({ status: 502 });
  });
});
