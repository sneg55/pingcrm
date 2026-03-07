import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";
import { Nav } from "@/components/nav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Ping CRM",
  description: "Your AI-powered networking assistant",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className} suppressHydrationWarning>
        <QueryProvider>
          <Nav />
          {children}
        </QueryProvider>
      </body>
    </html>
  );
}
