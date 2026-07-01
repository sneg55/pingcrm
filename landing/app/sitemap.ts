import type { MetadataRoute } from "next";

// Required by output: "export" so the route is emitted as a static file.
export const dynamic = "force-static";

// Emitted as a static out/sitemap.xml at build time (output: "export").
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: "https://pingcrm.xyz",
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1,
    },
  ];
}
