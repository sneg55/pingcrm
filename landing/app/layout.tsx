import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
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
