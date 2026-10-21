import { afterEach, describe, expect, it, vi } from "vitest";
const redisMock = vi.hoisted(() => ({ createClient: vi.fn() }));
vi.mock("redis", () => ({ createClient: redisMock.createClient }));

import { consumeUpstreamBudget, consumeUpstreamDailyBudget, consumeVisitorBudget, consumeVisitorDailyBudget, searchCacheKey, sharedRedis, visitorIdentity } from "../lib/redis";
import { isLaunched } from "../lib/launch";

afterEach(() => vi.unstubAllEnvs());

describe("launch and public limits", () => {
  it("keeps launch off unless explicitly enabled at runtime", () => {
    vi.stubEnv("OPENJOBS_PUBLIC_LAUNCH_ENABLED", "0");
    expect(isLaunched()).toBe(false);
    vi.stubEnv("OPENJOBS_PUBLIC_LAUNCH_ENABLED", "1");
    expect(isLaunched()).toBe(true);
  });

  it("hashes the edge client IP and shares an unknown bucket", () => {
    expect(visitorIdentity(new Headers({ "x-real-ip": "203.0.113.4" }))).toMatch(/^[a-f0-9]{32}$/);
    expect(visitorIdentity(new Headers({ "x-real-ip": "203.0.113.4" }))).toBe(visitorIdentity(new Headers({ "x-real-ip": "203.0.113.4" })));
    expect(visitorIdentity(new Headers({ "x-real-ip": "spoofed" }))).toBe(visitorIdentity(new Headers()));
  });

  it("defaults to a 60/min shared-key ceiling and clamps larger overrides", async () => {
    const evalMock = vi.fn(async () => 1);
    const redis = { eval: evalMock } as never;
    await expect(consumeVisitorBudget(redis, "visitor", 120_000)).resolves.toBe(true);
    expect((evalMock.mock.calls as unknown[][])[0][1]).toMatchObject({ arguments: ["25", "65"] });
    await expect(consumeVisitorDailyBudget(redis, "visitor", 120_000)).resolves.toBe(true);
    expect((evalMock.mock.calls as unknown[][])[1][1]).toMatchObject({ arguments: ["300", "86460"] });
    await expect(consumeUpstreamBudget(redis, 120_000)).resolves.toBe(true);
    expect((evalMock.mock.calls as unknown[][])[2][1]).toMatchObject({ arguments: ["60", "65"] });
    await expect(consumeUpstreamDailyBudget(redis, 120_000)).resolves.toBe(true);
    expect((evalMock.mock.calls as unknown[][])[3][1]).toMatchObject({ arguments: ["5000", "86460"] });
    vi.stubEnv("OPENJOBS_GLOBAL_LIMIT_PER_MINUTE", "9999");
    await consumeUpstreamBudget(redis, 120_000);
    expect((evalMock.mock.calls as unknown[][])[4][1]).toMatchObject({ arguments: ["420", "65"] });
    vi.stubEnv("OPENJOBS_GLOBAL_LIMIT_PER_DAY", "999999");
    await consumeUpstreamDailyBudget(redis, 120_000);
    expect((evalMock.mock.calls as unknown[][])[5][1]).toMatchObject({ arguments: ["20000", "86460"] });
    expect(searchCacheKey({ q: "one" })).not.toBe(searchCacheKey({ q: "two" }));
  });

  it("fails closed during a Redis outage and reconnects after the old client closes", async () => {
    vi.stubEnv("OPENJOBS_REDIS_URL", "redis://127.0.0.1:6379");
    const first = { on: vi.fn(), connect: vi.fn(async () => {}), isReady: true, isOpen: true };
    const recovered = { on: vi.fn(), connect: vi.fn(async () => {}), isReady: true, isOpen: true };
    redisMock.createClient.mockReturnValueOnce(first).mockReturnValueOnce(recovered);

    await expect(sharedRedis()).resolves.toBe(first);
    first.isReady = false;
    await expect(sharedRedis()).rejects.toThrow("Shared Redis is unavailable");
    first.isReady = true;
    await expect(sharedRedis()).resolves.toBe(first);

    first.isReady = false;
    first.isOpen = false;
    await expect(sharedRedis()).rejects.toThrow("Shared Redis is unavailable");
    await expect(sharedRedis()).resolves.toBe(recovered);
    expect(redisMock.createClient).toHaveBeenCalledTimes(2);
  });
});
