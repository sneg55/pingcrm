---
sidebar_position: 8
title: Map
description: "The PingCRM map plots contacts on an interactive world map to find nearby people while traveling and spot geographic clusters in your network."
---

# Map

The `/map` page plots your contacts on an interactive world map. Use it to find nearby contacts when you travel, to see where your network clusters, and to jump from a contact's location to the map.

![Map view with contacts plotted globally](/img/screenshots/map/overview.png)

## How it works

Every contact with a non-empty `location` string is geocoded to latitude and longitude through the Mapbox Geocoding API. The map queries contacts inside the current viewport and draws them as pins, clustering them in dense areas.

## Opening the map

There are two entry points:

1. **Sidebar nav**: the "Map" entry opens `/map` at a world view. Pan and zoom to fill the sidebar with the contacts in view.
2. **Contact page**: when a contact has been geocoded, the location text under their profile is a link. It opens `/map?focus=<contact_id>`, centered on that contact at city-level zoom.

![Map focused on a single contact](/img/screenshots/map/focus.png)

If a contact's location could not be geocoded (free-form text such as a URL, an emoji, or an unparseable entry), it shows as plain text on the contact page.

## Viewport sidebar

The right-hand sidebar lists the contacts in view, highest relationship score first. The list refreshes when a pan or zoom gesture ends (Mapbox `moveend`).

Each row shows the contact's avatar, name, and score. Clicking a row opens the contact page.

When more than 500 contacts are in view, the sidebar shows "Showing 500 of N, zoom in for more". `GET /api/v1/contacts/map` returns at most 500 contacts per request.

## Clustering

Zoomed-out views merge nearby pins into numbered cluster bubbles. Clicking a cluster zooms in and splits it. The cluster radius is 50 pixels. Clusters stop forming above zoom level 14, so individual pins appear from zoom 15.

![Cluster bubbles at zoomed-out view](/img/screenshots/map/cluster.png)

## Geocoding

A Celery task geocodes contacts in the background:

- **On write**: whenever a contact is created with a `location`, or its `location` changes (manual edit, LinkedIn, Google, or CSV import), a `geocode_contact` task is enqueued.
- **One-time backfill**: the `backfill_all_contacts` admin task enqueues every contact that has a location but no matching geocode.

The task is idempotent: it skips contacts whose stored `geocoded_location` already matches the current `location`. Clearing a contact's location clears its coordinates. Without `MAPBOX_SECRET_TOKEN` the worker skips geocoding and logs that the token is missing.

### Failure handling

| Mapbox response | Stored state | Behavior |
|---|---|---|
| 200 with a match | `latitude`, `longitude`, `geocoded_location`, `geocoded_at` all set | Pin rendered on map |
| 200 with zero results | `geocoded_at` set, lat/lng null | Contact hidden from map; no retry until location changes |
| 4xx | Same as zero results | Dropped; logged at warning (provider) and info (task) |
| 429 (rate limit) | Unchanged | Task retried with exponential backoff, up to 5 retries |
| 5xx / timeout | Unchanged | Retried up to 3 times inside the service, then by Celery with exponential backoff |

The task is rate limited to 500 per minute.

## Configuration

Setup needs two Mapbox tokens:

- `MAPBOX_SECRET_TOKEN`: used by the backend Celery worker for geocoding. Any valid Mapbox token works, since Mapbox has no dedicated geocoding scope. For minor separation you can create a secret token by ticking any secret scope in the Mapbox dashboard.
- `MAPBOX_PUBLIC_TOKEN`: returned to the browser by `GET /api/v1/map/config` and used by `react-map-gl` to load tiles. Restrict this token to your production domain and `localhost` in the Mapbox token settings so nobody else can use your quota.

If `MAPBOX_PUBLIC_TOKEN` is missing, `/map` shows a "Map is not yet configured" message instead of crashing.

## API surface

- `GET /api/v1/map/config` returns `{ data: { mapbox_public_token } }`. Requires auth.
- `GET /api/v1/contacts/map?bbox=minLng,minLat,maxLng,maxLat&limit=500` returns the authenticated user's contacts whose coordinates fall inside the bounding box. The response includes `meta.total_in_bounds`, which feeds the "Showing N of M" hint.
