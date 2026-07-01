import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://pingcrm.xyz"),
  alternates: {
    canonical: "/",
  },
  title: "PingCRM — Personal Networking CRM | AI-Powered, Open Source & Self-Hostable",
  description:
    "PingCRM is a personal networking CRM that syncs Gmail, Telegram, Twitter, and LinkedIn. AI-powered follow-ups, relationship scoring, and weekly digests — open source and self-hostable.",
  openGraph: {
    title: "PingCRM — Personal Networking CRM | AI-Powered & Open Source",
    description:
      "Personal networking CRM that syncs your conversations across Gmail, Telegram, Twitter, and LinkedIn. AI writes your follow-ups. Open source, self-hostable.",
    type: "website",
    url: "https://pingcrm.xyz",
    siteName: "PingCRM",
    images: [
      {
        url: "https://pingcrm.xyz/og.png",
        width: 1200,
        height: 630,
        alt: "PingCRM — Personal Networking CRM",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "PingCRM — Personal Networking CRM | AI-Powered & Open Source",
    description:
      "Sync Gmail, Telegram, Twitter, and LinkedIn. AI-powered follow-ups and relationship scoring. Open source, self-hostable.",
    images: ["https://pingcrm.xyz/og.png"],
  },
};

// JSON-LD structured data for search + AI answer engines. Truthful only —
// no aggregateRating/review (would be fabricated). FAQPage is added separately
// once visible on-page Q&A exists.
const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://pingcrm.xyz/#organization",
      name: "PingCRM",
      url: "https://pingcrm.xyz",
      logo: "https://pingcrm.xyz/og.png",
      sameAs: ["https://github.com/sneg55/pingcrm"],
    },
    {
      "@type": "WebSite",
      "@id": "https://pingcrm.xyz/#website",
      url: "https://pingcrm.xyz",
      name: "PingCRM",
      description:
        "Personal networking CRM that syncs Gmail, Telegram, Twitter, and LinkedIn with AI-powered follow-ups.",
      publisher: { "@id": "https://pingcrm.xyz/#organization" },
      inLanguage: "en",
    },
    {
      "@type": "SoftwareApplication",
      "@id": "https://pingcrm.xyz/#software",
      name: "PingCRM",
      applicationCategory: "BusinessApplication",
      applicationSubCategory: "Personal CRM",
      operatingSystem: "Web, Docker (self-hosted)",
      description:
        "PingCRM is an open-source, self-hostable personal networking CRM. It syncs conversations across Gmail, Telegram, Twitter/X, and LinkedIn into one timeline per contact, scores relationships, and uses Claude AI to draft follow-up messages.",
      url: "https://pingcrm.xyz",
      image: "https://pingcrm.xyz/og.png",
      license: "https://www.gnu.org/licenses/agpl-3.0.html",
      isAccessibleForFree: true,
      featureList: [
        "Multi-platform sync (Gmail, Telegram, Twitter/X, LinkedIn)",
        "AI-drafted follow-up messages",
        "Transparent relationship scoring",
        "Unified per-contact timeline",
        "Identity resolution across platforms",
        "Weekly digest of who to reach out to",
      ],
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
      publisher: { "@id": "https://pingcrm.xyz/#organization" },
    },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
        />
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-WVR19X9096" />
        <script
          dangerouslySetInnerHTML={{
            __html: `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag('js',new Date());gtag('config','G-WVR19X9096');`,
          }}
        />
      </head>
      <body className="antialiased min-h-screen">{children}</body>
    </html>
  );
}
