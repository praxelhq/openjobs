import { describe, expect, it, vi } from "vitest";
import { publishNextCursor, resolvePublicCursor } from "../lib/paging";
import { parseSearchQuery, SearchInputError } from "../lib/search";
import { RequestGeneration } from "../lib/request-generation";

function fakeRedis() {
  const values = new Map<string, string>();
  return {
    values,
    get: vi.fn(async (key: string) => values.get(key) ?? null),
    setEx: vi.fn(async (key: string, _ttl: number, value: string) => { values.set(key, value); return "OK"; })
  };
}

describe("public pagination", () => {
  it("hides upstream cursors, binds page tokens to filters, and stops at 96 results", async () => {
    const redis = fakeRedis();
    const query = parseSearchQuery(new URLSearchParams("q=designer&country=IN"));
    const page = await publishNextCursor(redis as never, query, 1, { jobs: [], nextCursor: "upstream-secret-cursor" });
    expect(page.nextCursor).toMatch(/^[A-Za-z0-9_-]{24}$/);
    expect(page.nextCursor).not.toBe("upstream-secret-cursor");
    expect(redis.setEx.mock.calls[0][1]).toBe(600);
    if (!page.nextCursor) throw new Error("A first page should have a public cursor");
    const resolved = await resolvePublicCursor(redis as never, { ...query, cursor: page.nextCursor });
    expect(resolved).toEqual({ upstreamCursor: "upstream-secret-cursor", pageNumber: 2 });
    await expect(resolvePublicCursor(redis as never, { ...query, country: "US", cursor: page.nextCursor })).rejects.toThrow(SearchInputError);
    const final = await publishNextCursor(redis as never, query, 4, { jobs: [], nextCursor: "another-upstream-cursor" });
    expect(final.nextCursor).toBeNull();
  });

  it("expires invalid links without calling upstream", async () => {
    const redis = fakeRedis();
    const query = parseSearchQuery(new URLSearchParams("cursor=notFound"));
    await expect(resolvePublicCursor(redis as never, query)).rejects.toThrow("expired");
  });
});

describe("in-flight search generation", () => {
  it("invalidates the old response before a new search state commits", async () => {
    const generation = new RequestGeneration();
    const oldRequest = generation.current();
    let visible = "";
    let resolveOld: ((value: string) => void) | undefined;
    const oldResponse = new Promise<string>((resolve) => { resolveOld = resolve; }).then((value) => {
      if (generation.isCurrent(oldRequest)) visible = value;
    });
    generation.invalidate();
    const newRequest = generation.current();
    if (!resolveOld) throw new Error("The old request did not start");
    resolveOld("stale designer result");
    await oldResponse;
    expect(visible).toBe("");
    if (generation.isCurrent(newRequest)) visible = "new empty-query result";
    expect(visible).toBe("new empty-query result");
  });
});
