import { NextResponse } from "next/server";
import { sharedRedis } from "@/lib/redis";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  if (!process.env.OPENJOBS_CONSUMER_SEARCH_KEY) {
    return NextResponse.json({ ready: false }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
  try {
    const redis = await sharedRedis();
    if (await redis.ping() === "PONG") return NextResponse.json({ ready: true }, { headers: { "Cache-Control": "no-store" } });
  } catch { /* Fail closed. */ }
  return NextResponse.json({ ready: false }, { status: 503, headers: { "Cache-Control": "no-store" } });
}
