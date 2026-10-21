import type { Metadata } from "next";
import "./styles.css";

function publicSiteUrl(): URL | null {
  try {
    const url = new URL(process.env.PUBLIC_SITE_URL ?? "");
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") return null;
    return url;
  } catch {
    return null;
  }
}

const site = publicSiteUrl();
const indexable = site?.hostname === "openjobs.praxyjobs.com" && process.env.OPENJOBS_PUBLIC_LAUNCH_ENABLED === "1";

export const metadata: Metadata = {
  title: "OpenJobs — find the role, go to the employer",
  description: "Search source-linked jobs from Praxy Jobs and open the original application. Free to browse, with no account required.",
  metadataBase: site ?? undefined,
  alternates: site ? { canonical: "/" } : undefined,
  openGraph: {
    title: "OpenJobs — find the role, go to the employer",
    description: "Search jobs from Praxy Jobs. Open the original application, with no account required.",
    url: site?.toString(),
    images: site ? [{ url: new URL("/openjobs-og.png", site).toString(), width: 1200, height: 630, alt: "OpenJobs — find the role, go to the employer" }] : undefined,
    type: "website"
  },
  twitter: site ? { card: "summary_large_image", images: [new URL("/openjobs-og.png", site).toString()] } : undefined,
  robots: { index: indexable, follow: indexable }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
