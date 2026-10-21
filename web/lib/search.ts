import { isIP } from "node:net";

export const UPSTREAM_SEARCH_URL = "https://praxyjobs.com/v1/internal/consumer/jobs/search";
export const PAGE_SIZE = 24;
const MAX_RESPONSE_BYTES = 1_000_000;

export type SearchQuery = { q: string; country: string; remote: "" | "only" | "exclude"; cursor: string };

export type PublicJob = {
  jobKey: string;
  title: string;
  organization: string;
  applyUrl: string;
  sourceHost: string;
  firstSeen: string;
  datePosted: string | null;
  location: string | null;
  workplace: string | null;
  remote: boolean | null;
  employmentType: string[];
  descriptionSnippet: string | null;
};

export type SearchPage = { jobs: PublicJob[]; nextCursor: string | null };

export class SearchInputError extends Error {}
export class SearchUpstreamError extends Error {
  constructor(readonly status: number) {
    super(`Praxy Jobs search returned ${status}`);
  }
}

function one(params: URLSearchParams, name: string): string {
  const values = params.getAll(name);
  if (values.length > 1) throw new SearchInputError(`Only one ${name} value is allowed.`);
  return values[0] ?? "";
}

export function parseSearchQuery(params: URLSearchParams): SearchQuery {
  const rawQ = one(params, "q");
  if ([...rawQ].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) throw new SearchInputError("Search text contains a control character.");
  const q = rawQ.trim().replace(/\s+/g, " ");
  const country = one(params, "country").trim().toUpperCase();
  const remote = one(params, "remote").trim();
  const cursor = one(params, "cursor").trim();
  if (q.length > 120) throw new SearchInputError("Search text is too long.");
  if (country && !/^[A-Z]{2}$/.test(country)) throw new SearchInputError("Country must be a two-letter code.");
  if (remote !== "" && remote !== "only" && remote !== "exclude") throw new SearchInputError("Invalid remote filter.");
  if (cursor.length > 64 || (cursor && !/^[A-Za-z0-9_-]+$/.test(cursor))) throw new SearchInputError("Invalid page cursor.");
  return { q, country, remote, cursor };
}

export function upstreamUrl(query: SearchQuery): URL {
  const url = new URL(UPSTREAM_SEARCH_URL);
  if (query.q) url.searchParams.set("q", query.q);
  if (query.country) url.searchParams.set("country", query.country);
  if (query.remote) url.searchParams.set("remote", query.remote);
  if (query.cursor) url.searchParams.set("cursor", query.cursor);
  url.searchParams.set("limit", String(PAGE_SIZE));
  return url;
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function required(value: unknown, max = 500): string {
  if (typeof value !== "string" || !value.trim() || value.length > max) throw new SearchUpstreamError(502);
  return value.trim();
}

function optional(value: unknown, max = 500): string | null {
  return typeof value === "string" && value.trim() ? value.trim().slice(0, max) : null;
}

function plainSnippet(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value
    .replace(/<\s*(script|style)\b[^>]*>[\s\S]*?<\/\s*\1\s*>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/<[^>]*$/g, " ")
    .replace(/%[A-Z][A-Z0-9_]+%/g, " ")
    .replace(/&(#(?:x[0-9a-f]+|[0-9]+)|amp|lt|gt|quot|apos|nbsp|mdash|ndash|rsquo|lsquo|rdquo|ldquo|hellip|bull);/gi, (_entity, code: string) => {
      if (code.startsWith("#")) {
        const hex = code[1]?.toLowerCase() === "x";
        const number = Number.parseInt(code.slice(hex ? 2 : 1), hex ? 16 : 10);
        return number > 0 && number <= 0x10ffff && (number < 0xd800 || number > 0xdfff)
          ? String.fromCodePoint(number)
          : " ";
      }
      return ({ amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", mdash: "—", ndash: "–", rsquo: "’", lsquo: "‘", rdquo: "”", ldquo: "“", hellip: "…", bull: "•" } as Record<string, string>)[code.toLowerCase()] ?? " ";
    })
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return null;
  const excerpt = text.slice(0, 320).trim();
  if (excerpt.length <= 160 || /[.!?…]$/.test(excerpt)) return excerpt;
  const lastSpace = excerpt.lastIndexOf(" ");
  return lastSpace > 120 ? `${excerpt.slice(0, lastSpace)}…` : excerpt;
}

function date(value: unknown, optionalDate = false): string | null {
  if (value == null && optionalDate) return null;
  const text = required(value, 50);
  if (Number.isNaN(Date.parse(text))) throw new SearchUpstreamError(502);
  return text;
}

function publicHttpsUrl(value: unknown): { url: string; host: string } {
  const raw = required(value, 8192);
  let parsed: URL;
  try { parsed = new URL(raw); } catch { throw new SearchUpstreamError(502); }
  const host = parsed.hostname.replace(/^\[|\]$/g, "");
  if (parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password ||
      isIP(host) !== 0 || !host.includes(".") || host === "localhost" || host.endsWith(".localhost") ||
      host.endsWith(".internal") || host.endsWith(".local")) throw new SearchUpstreamError(502);
  return { url: parsed.toString(), host: parsed.hostname.replace(/^www\./, "") };
}

export function parseConsumerPage(value: unknown): SearchPage {
  const page = record(value);
  if (!page) throw new SearchUpstreamError(502);
  if (page.schema_version !== "praxy-consumer-jobs-v1" || !Array.isArray(page.results) || page.results.length > 50) throw new SearchUpstreamError(502);
  const jobs = page.results.map((raw): PublicJob => {
    const item = record(raw);
    if (!item) throw new SearchUpstreamError(502);
    const apply = publicHttpsUrl(item.apply_url);
    const firstSeen = date(item.first_seen);
    if (!firstSeen) throw new SearchUpstreamError(502);
    return {
      jobKey: required(item.job_key, 255),
      title: required(item.title, 500),
      organization: required(item.organization, 500),
      applyUrl: apply.url,
      sourceHost: apply.host,
      firstSeen,
      datePosted: date(item.date_posted, true),
      location: optional(item.location, 250),
      workplace: optional(item.workplace, 100),
      remote: typeof item.remote === "boolean" ? item.remote : null,
      employmentType: Array.isArray(item.employment_type) ? item.employment_type.filter((v): v is string => typeof v === "string").slice(0, 8) : [],
      descriptionSnippet: plainSnippet(item.description_snippet)
    };
  });
  const nextCursor = page.next_cursor == null ? null : required(page.next_cursor, 4096);
  return { jobs, nextCursor };
}

async function boundedJson(response: Response): Promise<unknown> {
  const reader = response.body?.getReader();
  if (!reader) throw new SearchUpstreamError(502);
  let size = 0;
  const chunks: Uint8Array[] = [];
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE_BYTES) throw new SearchUpstreamError(502);
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try { return JSON.parse(new TextDecoder().decode(bytes)); } catch { throw new SearchUpstreamError(502); }
}

export async function fetchConsumerPage(query: SearchQuery, key: string, fetcher: typeof fetch = fetch): Promise<SearchPage> {
  if (!key) throw new SearchUpstreamError(503);
  let response: Response;
  try {
    response = await fetcher(upstreamUrl(query), {
      headers: { Accept: "application/json", "X-API-Key": key },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(8000)
    });
  } catch { throw new SearchUpstreamError(503); }
  if (!response.ok) throw new SearchUpstreamError(response.status);
  return parseConsumerPage(await boundedJson(response));
}
