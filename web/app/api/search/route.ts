import { type NextRequest, NextResponse } from "next/server";
import { consumeUpstreamBudget, consumeUpstreamDailyBudget, consumeVisitorBudget, consumeVisitorDailyBudget, searchCacheKey, sharedRedis, visitorIdentity } from "@/lib/redis";
import { isLaunched } from "@/lib/launch";
import { publishNextCursor, resolvePublicCursor } from "@/lib/paging";
import { fetchConsumerPage, parseSearchQuery, SearchInputError, SearchUpstreamError, type SearchPage, type SearchQuery } from "@/lib/search";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const headers = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };

function problem(status: number, message: string, retryAfter?: string) {
  return NextResponse.json({ ok: false, error: message }, {
    status,
    headers: retryAfter ? { ...headers, "Retry-After": retryAfter } : headers
  });
}

export async function GET(request: NextRequest) {
  if (!isLaunched()) return problem(404, "Not found.");
  let query: SearchQuery;
  try {
    query = parseSearchQuery(request.nextUrl.searchParams);
  } catch (error) {
    return problem(400, error instanceof SearchInputError ? error.message : "Invalid search request.");
  }
  if (!query.q) return problem(400, "Enter a role, skill, or company to search.");

  // This public route never accepts a caller-supplied upstream, key, or response shape.
  const key = process.env.OPENJOBS_CONSUMER_SEARCH_KEY;
  if (!key) return problem(503, "Search is temporarily unavailable.", "30");
  try {
    const redis = await sharedRedis();
    const visitor = visitorIdentity(request.headers);
    if (!await consumeVisitorBudget(redis, visitor)) {
      return problem(429, "Search limit reached. Please try again in a minute.", "60");
    }
    if (!await consumeVisitorDailyBudget(redis, visitor)) {
      return problem(429, "Search limit reached. Please try again later.", "3600");
    }
    const cacheKey = searchCacheKey(query);
    const cached = await redis.get(cacheKey);
    if (cached) {
      const page = JSON.parse(cached) as SearchPage;
      return NextResponse.json({ ok: true, data: page }, { headers });
    }
    const { upstreamCursor, pageNumber } = await resolvePublicCursor(redis, query);
    if (!await consumeUpstreamBudget(redis)) return problem(429, "Search is busy. Please try again in a minute.", "60");
    if (!await consumeUpstreamDailyBudget(redis)) return problem(429, "Search is busy. Please try again later.", "3600");
    const upstream = await fetchConsumerPage({ ...query, cursor: upstreamCursor }, key);
    const page = await publishNextCursor(redis, query, pageNumber, upstream);
    await redis.setEx(cacheKey, 20, JSON.stringify(page));
    return NextResponse.json({ ok: true, data: page }, { headers });
  } catch (error) {
    if (error instanceof SearchInputError) return problem(400, error.message);
    if (error instanceof SearchUpstreamError && error.status === 400) return problem(400, "That page is no longer valid. Start a new search.");
    // Authentication, upstream, and Redis failures have the same public shape.
    // Never include upstream response bodies or environment values in output.
    return problem(503, "Search is temporarily unavailable.", "30");
  }
}
