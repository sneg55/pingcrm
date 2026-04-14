"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import type { MapRef } from "react-map-gl/mapbox";
import type { MapMouseEvent } from "mapbox-gl";
import Map, { Layer, Marker, Source } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

import type { components } from "@/lib/api-types";
import type { Bbox } from "@/hooks/use-viewport-contacts";

type Pin = components["schemas"]["ContactMapPin"];

export interface ContactMapProps {
  token: string;
  pins: Pin[];
  focus?: { latitude: number; longitude: number } | null;
  onViewportChange: (bbox: Bbox) => void;
  onPinClick: (pin: Pin) => void;
  hoveredId: string | null;
}

const SOURCE_ID = "contact-pins";

export function ContactMap({
  token,
  pins,
  focus,
  onViewportChange,
  onPinClick,
  hoveredId,
}: ContactMapProps) {
  const mapRef = useRef<MapRef | null>(null);
  const [initial] = useState(() =>
    focus
      ? { longitude: focus.longitude, latitude: focus.latitude, zoom: 10 }
      : { longitude: 0, latitude: 20, zoom: 1.5 },
  );

  const geojson = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: pins.map((p) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: [p.longitude, p.latitude],
        },
        properties: {
          id: p.id,
          name: p.full_name,
          score: p.relationship_score,
        },
      })),
    }),
    [pins],
  );

  const hoveredPin = useMemo(
    () => (hoveredId ? pins.find((p) => p.id === hoveredId) ?? null : null),
    [hoveredId, pins],
  );

  const emitBounds = useCallback(() => {
    const m = mapRef.current;
    if (!m) return;
    const b = m.getMap().getBounds();
    if (!b) return;
    onViewportChange({
      minLng: b.getWest(),
      minLat: b.getSouth(),
      maxLng: b.getEast(),
      maxLat: b.getNorth(),
    });
  }, [onViewportChange]);

  const handleClick = useCallback(
    (e: MapMouseEvent) => {
      const feature = e.features?.[0];
      if (!feature) return;
      if (feature.layer?.id === "clusters") {
        const clusterId = feature.properties?.cluster_id;
        const src = mapRef.current?.getMap().getSource(SOURCE_ID) as
          | { getClusterExpansionZoom: (id: number, cb: (err: unknown, zoom: number) => void) => void }
          | undefined;
        src?.getClusterExpansionZoom(clusterId, (err: unknown, zoom: number) => {
          if (err) return;
          const coords = (feature.geometry as unknown as { coordinates: [number, number] }).coordinates;
          mapRef.current?.easeTo({ center: coords, zoom });
        });
        return;
      }
      if (feature.layer?.id === "unclustered-point") {
        const id = feature.properties?.id as string;
        const pin = pins.find((p) => p.id === id);
        if (pin) onPinClick(pin);
      }
    },
    [pins, onPinClick],
  );

  return (
    <Map
      ref={mapRef}
      mapboxAccessToken={token}
      initialViewState={initial}
      mapStyle="mapbox://styles/mapbox/streets-v12"
      onLoad={emitBounds}
      onMoveEnd={emitBounds}
      onClick={handleClick}
      interactiveLayerIds={["clusters", "unclustered-point"]}
      style={{ width: "100%", height: "100%" }}
    >
      <Source
        id={SOURCE_ID}
        type="geojson"
        data={geojson}
        cluster
        clusterMaxZoom={14}
        clusterRadius={50}
      >
        <Layer
          id="clusters"
          type="circle"
          filter={["has", "point_count"]}
          paint={{
            "circle-color": "#0d9488",
            "circle-radius": [
              "step",
              ["get", "point_count"],
              16,
              10,
              22,
              50,
              30,
            ],
            "circle-opacity": 0.85,
          }}
        />
        <Layer
          id="cluster-count"
          type="symbol"
          filter={["has", "point_count"]}
          layout={{
            "text-field": ["get", "point_count_abbreviated"],
            "text-size": 12,
          }}
          paint={{ "text-color": "#fff" }}
        />
        <Layer
          id="unclustered-point"
          type="circle"
          filter={["!", ["has", "point_count"]]}
          paint={{
            "circle-color": [
              "case",
              ["==", ["get", "id"], hoveredId ?? ""],
              "#dc2626",
              "#0d9488",
            ],
            "circle-radius": 7,
            "circle-stroke-width": 2,
            "circle-stroke-color": "#fff",
          }}
        />
      </Source>
      {hoveredPin && (
        <Marker
          longitude={hoveredPin.longitude}
          latitude={hoveredPin.latitude}
          anchor="center"
        >
          <div className="relative pointer-events-none">
            <span className="absolute inset-0 -m-2 rounded-full bg-red-500/30 animate-ping" />
            <span className="block h-4 w-4 rounded-full bg-red-600 ring-2 ring-white shadow" />
          </div>
        </Marker>
      )}
    </Map>
  );
}
