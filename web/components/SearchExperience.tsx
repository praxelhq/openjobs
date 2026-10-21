"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import type { PublicJob, SearchPage } from "@/lib/search";
import { RequestGeneration } from "@/lib/request-generation";

type Filters = { q: string; country: string; remote: string };

function filtersFrom(params: URLSearchParams): Filters {
  const remote = params.get("remote") ?? "";
  const country = params.has("country") ? (params.get("country") ?? "") : params.has("q") ? "" : "IN";
  return {
    q: (params.get("q")?.trim() || "engineer").slice(0, 120),
    country: country.toUpperCase().slice(0, 2),
    remote: remote === "only" || remote === "exclude" ? remote : ""
  };
}

function queryString(filters: Filters, cursor = "") {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.country) params.set("country", filters.country);
  if (filters.remote) params.set("remote", filters.remote);
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}

function publicSearchFallback(filters: Filters) {
  const params = queryString(filters);
  return `https://praxy.me/jobs${params ? `?${params}` : ""}`;
}

function dateLabel(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function workplaceLabel(value: string | null) {
  switch (value?.toLowerCase()) {
    case "on_site":
    case "onsite":
    case "on-site":
      return "On-site";
    case "hybrid":
      return "Hybrid";
    case "remote":
      return "Remote";
    default:
      return null;
  }
}

function ArrowIcon() {
  return <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 10h11m-5-5 5 5-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function SearchIcon() {
  return <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="8.6" cy="8.6" r="5.35" stroke="currentColor" strokeWidth="1.6"/><path d="m12.8 12.8 4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>;
}

function JobCard({ job }: { job: PublicJob }) {
  const posted = dateLabel(job.datePosted);
  const firstSeen = dateLabel(job.firstSeen);
  const meta = [...new Set([job.location, job.remote === true ? "Remote" : null, workplaceLabel(job.workplace), job.employmentType[0]?.replaceAll("_", " ")].filter((item): item is string => Boolean(item)))];
  return <article className="job-row">
    <div className="job-main">
      <div className="job-company"><span className="company-marker" aria-hidden="true">{job.organization.charAt(0).toUpperCase()}</span>{job.organization}</div>
      <h3><a href={job.applyUrl} target="_blank" rel="noopener noreferrer">{job.title}<span className="sr-only"> at {job.organization}, original application opens in a new tab</span></a></h3>
      {(posted || firstSeen || meta.length > 0) && <div className="job-meta">{posted ? <span className="job-date">Posted {posted}</span> : firstSeen ? <span className="job-date">First seen {firstSeen}</span> : null}{meta.map((item) => <span key={item}>{item}</span>)}</div>}
      {job.descriptionSnippet && <p className="job-snippet">{job.descriptionSnippet}</p>}
      <div className="job-source">
        <span className="source-dot" aria-hidden="true" />
        <span>Original listing: <a href={job.applyUrl} target="_blank" rel="noopener noreferrer">{job.sourceHost}</a></span>
      </div>
    </div>
    <a className="apply-link" href={job.applyUrl} target="_blank" rel="noopener noreferrer" aria-label={`Open original application for ${job.title} at ${job.organization}`}>
      <span>View role</span><ArrowIcon />
    </a>
  </article>;
}

function Skeleton() {
  return <div className="skeleton-list" aria-label="Loading jobs" role="status">
    {[0, 1, 2].map((item) => <div className="skeleton-row" key={item}><span className="skeleton-line short"/><span className="skeleton-line title"/><span className="skeleton-line medium"/></div>)}
  </div>;
}

export function SearchExperience() {
  const urlParams = useSearchParams();
  const [active, setActive] = useState<Filters>(() => filtersFrom(new URLSearchParams(urlParams.toString())));
  const [draft, setDraft] = useState<Filters>(active);
  const [cursors, setCursors] = useState<string[]>([""]);
  const [pageIndex, setPageIndex] = useState(0);
  const [page, setPage] = useState<SearchPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const generation = useRef(new RequestGeneration());
  const cursor = cursors[pageIndex] ?? "";

  const prepareSearch = useCallback(() => {
    generation.current.invalidate();
    setLoading(true);
    setError(null);
    setNotice(null);
    setPage(null);
  }, []);

  useEffect(() => {
    const onBack = () => {
      const next = filtersFrom(new URLSearchParams(window.location.search));
      prepareSearch();
      setActive(next);
      setDraft(next);
      setCursors([""]);
      setPageIndex(0);
    };
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, [prepareSearch]);

  useEffect(() => {
    const controller = new AbortController();
    const requestGeneration = generation.current.current();
    const qs = queryString(active, cursor);
    fetch(`/api/search${qs ? `?${qs}` : ""}`, { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json() as { ok?: boolean; data?: SearchPage };
        if (response.status === 400 && cursor) {
          if (!controller.signal.aborted && generation.current.isCurrent(requestGeneration)) {
            generation.current.invalidate();
            setNotice("That page expired. Showing the first page of your search.");
            setCursors([""]);
            setPageIndex(0);
          }
          return null;
        }
        if (!response.ok || !payload.ok || !payload.data || !Array.isArray(payload.data.jobs)) {
          throw new Error(response.status === 429 ? "Search limit reached. Try again in a minute." : "Search is temporarily unavailable. Please try again.");
        }
        return payload.data;
      })
      .then((data) => { if (data && !controller.signal.aborted && generation.current.isCurrent(requestGeneration)) setPage(data); })
      .catch((cause: unknown) => { if (!controller.signal.aborted && generation.current.isCurrent(requestGeneration)) setError(cause instanceof Error && cause.message.startsWith("Search limit reached") ? cause.message : "Search is temporarily unavailable. Please try again."); })
      .finally(() => { if (!controller.signal.aborted && generation.current.isCurrent(requestGeneration)) setLoading(false); });
    return () => controller.abort();
  }, [active, cursor]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = { q: draft.q.trim(), country: draft.country, remote: draft.remote };
    if (!next.q) {
      setFormError("Enter a role, skill, or company to search.");
      return;
    }
    setFormError(null);
    const params = queryString(next);
    prepareSearch();
    window.history.pushState(null, "", `${window.location.pathname}${params ? `?${params}` : ""}`);
    setActive(next);
    setCursors([""]);
    setPageIndex(0);
  }

  function nextPage() {
    const nextCursor = page?.nextCursor;
    if (!nextCursor) return;
    prepareSearch();
    setCursors((values) => [...values.slice(0, pageIndex + 1), nextCursor]);
    setPageIndex((index) => index + 1);
    document.querySelector("#results")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function previousPage() {
    prepareSearch();
    setPageIndex((index) => Math.max(0, index - 1));
    document.querySelector("#results")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return <div className="site-wrap">
    <header className="site-header page-shell">
      <a href="/" className="brand" aria-label="OpenJobs by Praxy home"><Image className="praxy-wordmark" src="/praxy-wordmark-ink.svg" alt="Praxy" width={123} height={23} /><span className="brand-divider" aria-hidden="true"/><span className="brand-product">openjobs</span></a>
      <nav aria-label="Main navigation"><a href="https://praxyjobs.com" target="_blank" rel="noopener noreferrer">Praxy Jobs</a><a href="https://github.com/praxelhq/openjobs" target="_blank" rel="noopener noreferrer">View the code <span aria-hidden="true">↗</span></a></nav>
    </header>

    <main>
      <section className="hero page-shell" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-signal"/> Open search · Original applications</div>
          <h1 id="hero-title">Find the role.<br/><em>Go to the employer.</em></h1>
          <p>Search jobs from Praxy Jobs, then open the original application. Free to browse. No account required.</p>
        </div>
        <div className="hero-aside" aria-hidden="true"><span className="hero-aside-mark">↗</span><span>Original links, every time.</span></div>
      </section>

      <section className="search-band" aria-label="Search jobs">
        <div className="page-shell">
          <form onSubmit={submit} className="search-form">
            <label className="search-query"><span className="field-label">ROLE, SKILL, OR COMPANY</span><span className="query-control"><SearchIcon/><input name="q" type="search" value={draft.q} onChange={(event) => { setFormError(null); setDraft({ ...draft, q: event.target.value }); }} placeholder="Try product designer or Python" maxLength={120} autoComplete="off" /></span></label>
            <label className="search-select"><span className="field-label">COUNTRY</span><select value={draft.country} onChange={(event) => { setFormError(null); setDraft({ ...draft, country: event.target.value }); }}><option value="">Anywhere</option><option value="IN">India</option><option value="US">United States</option><option value="GB">United Kingdom</option><option value="CA">Canada</option><option value="DE">Germany</option><option value="SG">Singapore</option><option value="AE">UAE</option><option value="AU">Australia</option></select></label>
            <label className="search-select"><span className="field-label">WORKPLACE</span><select value={draft.remote} onChange={(event) => setDraft({ ...draft, remote: event.target.value })}><option value="">All roles</option><option value="only">Remote only</option><option value="exclude">Exclude remote</option></select></label>
            <button className="search-button" type="submit"><span>Search jobs</span><ArrowIcon/></button>
          </form>
          {formError && <p className="form-error" role="alert">{formError}</p>}
        </div>
      </section>

      <section id="results" className="results page-shell" aria-live="polite">
        <div className="results-heading"><div><div className="section-kicker">FROM PRAXY JOBS</div><h2>{active.q ? `Results for “${active.q}”` : "Browse jobs"}</h2><p>{active.country ? `Country: ${active.country}` : "Across locations"}{active.remote === "only" ? " · Remote only" : active.remote === "exclude" ? " · Excluding remote" : ""} · Best matches</p></div><div className="results-counter">{loading ? "Finding roles…" : page ? `${page.jobs.length} ${page.jobs.length === 1 ? "role" : "roles"} shown` : ""}</div></div>

        {notice && <p className="search-notice" role="status">{notice}</p>}

        {loading && <Skeleton />}
        {!loading && error && <div className="state-panel"><div className="state-mark">!</div><h3>We couldn’t load this search.</h3><p>{error}</p><div className="state-actions"><button type="button" onClick={() => { prepareSearch(); setActive({ ...active }); }}>Try again</button><a href={publicSearchFallback(active)} target="_blank" rel="noopener noreferrer">Search on Praxy <ArrowIcon/></a></div></div>}
        {!loading && !error && page?.jobs.length === 0 && <div className="state-panel"><div className="state-mark">0</div><h3>No roles in this search yet.</h3><p>Try a broader title, another country, or all workplace types.</p><button type="button" onClick={() => { prepareSearch(); setDraft({ q: "engineer", country: "IN", remote: "" }); window.history.pushState(null, "", "/"); setActive({ q: "engineer", country: "IN", remote: "" }); setCursors([""]); setPageIndex(0); }}>Clear filters</button></div>}
        {!loading && !error && page && page.jobs.length > 0 && <><div className="job-list">{page.jobs.map((job) => <JobCard key={job.jobKey} job={job}/>)}</div>{(pageIndex > 0 || page.nextCursor) && <div className="pagination"><span>Page {pageIndex + 1}</span><div><button type="button" onClick={previousPage} disabled={pageIndex === 0}>← Previous</button><button type="button" onClick={nextPage} disabled={!page.nextCursor}>Next page →</button></div></div>}{page.jobs.length === 24 && !page.nextCursor && <p className="result-limit-note">Showing a selection of matching roles. <a href={publicSearchFallback(active)} target="_blank" rel="noopener noreferrer">Continue on Praxy <ArrowIcon/></a></p>}</>}
      </section>
    </main>

    <footer className="site-footer"><div className="page-shell footer-inner"><div><div className="footer-brand">openjobs</div><p>A public job search built with <a href="https://praxyjobs.com">Praxy Jobs</a> data.</p></div><div className="footer-links"><a href="https://github.com/praxelhq/openjobs">Code &amp; docs ↗</a><a href="https://praxyjobs.com/data-license">Data terms ↗</a><a href="https://praxyjobs.com">Praxy Jobs ↗</a></div></div></footer>
  </div>;
}
