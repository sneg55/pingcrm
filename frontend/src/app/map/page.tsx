"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";

import { MapSidebar } from "@/components/map/map-sidebar";
import { ContactPinPopover } from "@/components/map/contact-pin-popover";
import { useMapConfig } from "@/hooks/use-map-config";
import { useViewportContacts, type Bbox } from "@/hooks/use-viewport-contacts";
import { client } from "@/lib/api-client";
import type { components } from "@/lib/api-types";

type Pin = components["schemas"]["ContactMapPin"];

const ContactMap = dynamic(
  () => import("@/components/map/contact-map").then((m) => m.ContactMap),
  { ssr: false, loading: () => <div className="h-full w-full bg-stone-50 dark:bg-stone-900" /> },
);

function MapPageInner() {
  const { data: config, isLoading: configLoading } = useMapConfig();
  const searchParams = useSearchParams();
  const focusId = searchParams.get("focus");
  const [focus, setFocus] = useState<{ latitude: number; longitude: number } | null>(null);
  const [bbox, setBbox] = useState<Bbox | null>(null);
  const [selected, setSelected] = useState<Pin | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  useEffect(() => {
    if (!focusId) return;
    let cancelled = false;
    (async () => {
      const { data } = await client.GET("/api/v1/contacts/{contact_id}", {
        params: { path: { contact_id: focusId } },
      });
      if (cancelled) return;
      const c = data?.data;
      if (c && c.latitude != null && c.longitude != null) {
        setFocus({ latitude: c.latitude, longitude: c.longitude });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [focusId]);

  const onViewport = useCallback((b: Bbox) => setBbox(b), []);
  const { data: viewportData } = useViewportContacts(bbox);
  const pins = (viewportData?.data ?? []) as Pin[];
  const total = (viewportData?.meta as { total_in_bounds?: number } | null)?.total_in_bounds ?? 0;

  if (configLoading) return <div className="p-8">Loading map…</div>;
  if (!config?.mapbox_public_token) {
    return (
      <div className="p-8 text-stone-600 dark:text-stone-300">
        Map is not yet configured. Ask an admin to set{" "}
        <code>MAPBOX_PUBLIC_TOKEN</code>.
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      <div className="flex-1 relative">
        <ContactMap
          token={config.mapbox_public_token}
          pins={pins}
          focus={focus}
          onViewportChange={onViewport}
          onPinClick={setSelected}
          hoveredId={hoveredId}
        />
        {selected && (
          <div className="absolute top-4 left-4 z-10">
            <ContactPinPopover pin={selected} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
      <MapSidebar
        pins={pins}
        totalInBounds={total}
        onHover={setHoveredId}
        selectedId={selected?.id ?? null}
      />
    </div>
  );
}

export default function MapPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading map…</div>}>
      <MapPageInner />
    </Suspense>
  );
}
