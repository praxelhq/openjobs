import { Suspense } from "react";
import { notFound } from "next/navigation";
import { SearchExperience } from "@/components/SearchExperience";
import { isLaunched } from "@/lib/launch";

export const dynamic = "force-dynamic";

export default function Page() {
  if (!isLaunched()) notFound();
  return <Suspense fallback={<main className="page-shell"><p className="loading-note">Opening search…</p></main>}><SearchExperience /></Suspense>;
}
