import { createHash, randomBytes } from "node:crypto";
import { SearchInputError, type SearchPage, type SearchQuery } from "./search";
import type { sharedRedis } from "./redis";

type Redis = Awaited<ReturnType<typeof sharedRedis>>;
const MAX_PUBLIC_PAGES = 4;
const CURSOR_TTL_SECONDS = 600;

function binding(query: SearchQuery): string {
  return createHash("sha256").update(JSON.stringify({ q: query.q, country: query.country, remote: query.remote })).digest("hex");
}

export async function resolvePublicCursor(redis: Redis, query: SearchQuery): Promise<{ upstreamCursor: string; pageNumber: number }> {
  if (!query.cursor) return { upstreamCursor: "", pageNumber: 1 };
  const raw = await redis.get(`openjobs:web:cursor:${query.cursor}`);
  if (!raw) throw new SearchInputError("This page link has expired. Start a new search.");
  let record: unknown;
  try { record = JSON.parse(raw); } catch { throw new SearchInputError("Invalid page link."); }
  if (!record || typeof record !== "object" || Array.isArray(record)) throw new SearchInputError("Invalid page link.");
  const data = record as Record<string, unknown>;
  if (data.version !== 1 || data.binding !== binding(query) || typeof data.upstreamCursor !== "string" ||
      !data.upstreamCursor || data.upstreamCursor.length > 4096 || !Number.isInteger(data.pageNumber) ||
      (data.pageNumber as number) < 2 || (data.pageNumber as number) > MAX_PUBLIC_PAGES) {
    throw new SearchInputError("Invalid page link for these filters.");
  }
  return { upstreamCursor: data.upstreamCursor, pageNumber: data.pageNumber as number };
}

export async function publishNextCursor(redis: Redis, query: SearchQuery, pageNumber: number, upstream: SearchPage): Promise<SearchPage> {
  if (!upstream.nextCursor || pageNumber >= MAX_PUBLIC_PAGES) return { ...upstream, nextCursor: null };
  const token = randomBytes(18).toString("base64url");
  await redis.setEx(`openjobs:web:cursor:${token}`, CURSOR_TTL_SECONDS, JSON.stringify({
    version: 1,
    binding: binding(query),
    upstreamCursor: upstream.nextCursor,
    pageNumber: pageNumber + 1
  }));
  return { ...upstream, nextCursor: token };
}
