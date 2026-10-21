import { createHash } from "node:crypto";
import { isIP } from "node:net";
import { createClient } from "redis";

function createSharedClient(url: string) {
  return createClient({
    url,
    socket: {
      connectTimeout: 1500,
      reconnectStrategy: (retries) => retries < 5 ? Math.min(100 * 2 ** retries, 1500) : new Error("Shared Redis reconnect limit reached")
    }
  });
}

let pending: Promise<ReturnType<typeof createSharedClient>> | undefined;

export async function sharedRedis() {
  const url = process.env.OPENJOBS_REDIS_URL;
  if (!url || !/^rediss?:\/\//.test(url)) throw new Error("Shared Redis is not configured");
  if (!pending) {
    const client = createSharedClient(url);
    // A connection failure is handled by the awaiting request; never log the URL.
    client.on("error", () => {});
    pending = client.connect().then(() => client).catch((error: unknown) => {
      pending = undefined;
      throw error;
    });
  }
  const client = await pending;
  if (!client.isReady) {
    // A closed client has exhausted reconnects. The next request may establish
    // a fresh connection after Redis returns; this request still fails closed.
    if (!client.isOpen) pending = undefined;
    throw new Error("Shared Redis is unavailable");
  }
  return client;
}

/** Railway overwrites X-Real-IP with the connecting client IP at its edge. */
export function visitorIdentity(headers: Headers): string {
  const value = headers.get("x-real-ip")?.trim() ?? "";
  const ip = isIP(value) ? value : "unknown";
  return createHash("sha256").update(ip).digest("hex").slice(0, 32);
}

const RATE_SCRIPT = `
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if count >= tonumber(ARGV[1]) then return 0 end
if redis.call('INCR', KEYS[1]) == 1 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2])) end
return 1
`;

async function consumeBudget(redis: Awaited<ReturnType<typeof sharedRedis>>, key: string, limit: number, ttl: number): Promise<boolean> {
  const result = await redis.eval(RATE_SCRIPT, { keys: [key], arguments: [String(limit), String(ttl)] });
  return result === 1;
}

export async function consumeVisitorBudget(redis: Awaited<ReturnType<typeof sharedRedis>>, visitor: string, now = Date.now()): Promise<boolean> {
  const minute = Math.floor(now / 60_000);
  return consumeBudget(redis, `openjobs:web:visitor:${visitor}:${minute}`, 25, 65);
}

export async function consumeVisitorDailyBudget(redis: Awaited<ReturnType<typeof sharedRedis>>, visitor: string, now = Date.now()): Promise<boolean> {
  const day = Math.floor(now / 86_400_000);
  return consumeBudget(redis, `openjobs:web:visitor-day:${visitor}:${day}`, 300, 86_460);
}

export async function consumeUpstreamBudget(redis: Awaited<ReturnType<typeof sharedRedis>>, now = Date.now()): Promise<boolean> {
  const minute = Math.floor(now / 60_000);
  // The default is deliberately low while this app shares another first-party key.
  // A dedicated scoped key can raise the global ceiling, never above 420/minute.
  const requestedLimit = Number(process.env.OPENJOBS_GLOBAL_LIMIT_PER_MINUTE ?? "60");
  const globalLimit = Number.isInteger(requestedLimit) ? Math.min(420, Math.max(1, requestedLimit)) : 60;
  return consumeBudget(redis, `openjobs:web:upstream:${minute}`, globalLimit, 65);
}

export async function consumeUpstreamDailyBudget(redis: Awaited<ReturnType<typeof sharedRedis>>, now = Date.now()): Promise<boolean> {
  const day = Math.floor(now / 86_400_000);
  const requestedLimit = Number(process.env.OPENJOBS_GLOBAL_LIMIT_PER_DAY ?? "5000");
  const globalLimit = Number.isInteger(requestedLimit) ? Math.min(20_000, Math.max(1, requestedLimit)) : 5000;
  return consumeBudget(redis, `openjobs:web:upstream-day:${day}`, globalLimit, 86_460);
}

export function searchCacheKey(query: object): string {
  return `openjobs:web:search:${createHash("sha256").update(JSON.stringify(query)).digest("hex")}`;
}
