import type { MetadataRoute } from "next";

// Required by output: "export" so the route is emitted as a static file.
export const dynamic = "force-static";

// Emitted as a static out/robots.txt at build time (output: "export").
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: "https://pingcrm.xyz/sitemap.xml",
    host: "https://pingcrm.xyz",
  };
}
