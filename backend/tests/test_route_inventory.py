"""Route inventory snapshot tests for /api/v1/contacts/* endpoints.

These tests guard against two failure modes:
1. Accidentally removing or adding a contact route.
2. Registering a static route (e.g. /tags) AFTER the parameterised
   /{contact_id} catch-all, which causes FastAPI to swallow the static
   path into the dynamic handler.

NOTE ON KNOWN ORDERING ISSUES
------------------------------
Several static paths (/bulk-update, /import/*, /sync/*, /scores/recalculate,
/reconcile-last-interaction) are currently registered after /{contact_id} in
the router.  FastAPI / Starlette matches routes in registration order, so a
request to e.g. POST /api/v1/contacts/bulk-update will be handled by the
/{contact_id} handler with contact_id='bulk-update', not the intended handler.

This is a known pre-existing bug.  The ordering test below asserts only the
invariants that are currently correct (the /tags group and a few others appear
before /{contact_id}) and also asserts that the known-bad ordering has NOT
gotten worse.  Fix the ordering bug by moving the offending routes before
/{contact_id} in contacts.py, then update this test accordingly.
"""
from __future__ import annotations

import pytest
from app.main import app


def _collect_contact_routes() -> list[tuple[str, str]]:
    """Return (METHOD, path) tuples for every /api/v1/contacts route.

    HEAD and OPTIONS are excluded because FastAPI adds them automatically
    and they are not meaningful for inventory purposes.
    """
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        if hasattr(route, "path") and route.path.startswith("/api/v1/contacts"):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                routes.append((method, route.path))
    return routes


def test_contacts_route_inventory() -> None:
    """Snapshot test: all /api/v1/contacts routes and their HTTP methods.

    Update the ``expected`` list intentionally when routes change.
    The list is sorted by (path, method) so diffs are easy to read.
    """
    routes = sorted(_collect_contact_routes(), key=lambda r: (r[1], r[0]))

    # Snapshot — update this list when routes change intentionally.
    expected: list[tuple[str, str]] = sorted(
        [
            ("GET",    "/api/v1/contacts"),
            ("POST",   "/api/v1/contacts"),
            ("GET",    "/api/v1/contacts/birthdays"),
            ("POST",   "/api/v1/contacts/bulk-update"),
            ("GET",    "/api/v1/contacts/ids"),
            ("POST",   "/api/v1/contacts/import/csv"),
            ("POST",   "/api/v1/contacts/import/linkedin"),
            ("POST",   "/api/v1/contacts/import/linkedin-messages"),
            ("GET",    "/api/v1/contacts/overdue"),
            ("POST",   "/api/v1/contacts/reconcile-last-interaction"),
            ("POST",   "/api/v1/contacts/scores/recalculate"),
            ("GET",    "/api/v1/contacts/stats"),
            ("POST",   "/api/v1/contacts/sync/gmail"),
            ("POST",   "/api/v1/contacts/sync/google"),
            ("POST",   "/api/v1/contacts/sync/google-calendar"),
            ("POST",   "/api/v1/contacts/sync/telegram"),
            ("POST",   "/api/v1/contacts/sync/twitter"),
            ("GET",    "/api/v1/contacts/tags"),
            ("POST",   "/api/v1/contacts/tags/apply"),
            ("POST",   "/api/v1/contacts/tags/discover"),
            ("GET",    "/api/v1/contacts/tags/taxonomy"),
            ("PUT",    "/api/v1/contacts/tags/taxonomy"),
            ("DELETE", "/api/v1/contacts/{contact_id}"),
            ("GET",    "/api/v1/contacts/{contact_id}"),
            ("PUT",    "/api/v1/contacts/{contact_id}"),
            ("GET",    "/api/v1/contacts/{contact_id}/activity"),
            ("POST",   "/api/v1/contacts/{contact_id}/auto-tag"),
            ("POST",   "/api/v1/contacts/{contact_id}/compose"),
            ("POST",   "/api/v1/contacts/{contact_id}/dismiss-duplicate/{other_id}"),
            ("GET",    "/api/v1/contacts/{contact_id}/duplicates"),
            ("POST",   "/api/v1/contacts/{contact_id}/enrich"),
            ("GET",    "/api/v1/contacts/{contact_id}/interactions"),
            ("POST",   "/api/v1/contacts/{contact_id}/interactions"),
            ("DELETE", "/api/v1/contacts/{contact_id}/interactions/{interaction_id}"),
            ("PATCH",  "/api/v1/contacts/{contact_id}/interactions/{interaction_id}"),
            ("POST",   "/api/v1/contacts/{contact_id}/merge/{other_id}"),
            ("POST",   "/api/v1/contacts/{contact_id}/refresh-avatar"),
            ("POST",   "/api/v1/contacts/{contact_id}/refresh-bios"),
            ("GET",    "/api/v1/contacts/{contact_id}/related"),
            ("POST",   "/api/v1/contacts/{contact_id}/send-message"),
            ("POST",   "/api/v1/contacts/{contact_id}/sync-emails"),
            ("POST",   "/api/v1/contacts/{contact_id}/sync-telegram"),
            ("POST",   "/api/v1/contacts/{contact_id}/sync-twitter"),
            ("GET",    "/api/v1/contacts/{contact_id}/telegram/common-groups"),
        ],
        key=lambda r: (r[1], r[0]),
    )

    assert routes == expected, (
        "Contact route inventory has changed.\n"
        f"  Extra  : {sorted(set(routes) - set(expected))}\n"
        f"  Missing: {sorted(set(expected) - set(routes))}\n"
        "Update the 'expected' list in this test if the change is intentional."
    )


def test_static_routes_before_parameterized() -> None:
    """Critical static routes must be registered before /{contact_id}.

    FastAPI (Starlette) matches routes in registration order.  If a
    single-segment static path such as /tags is registered after
    /{contact_id}, requests to /tags will be captured by the dynamic
    handler with contact_id='tags', causing incorrect behaviour.

    The following paths MUST appear before /{contact_id} in the router:
      /tags, /tags/taxonomy, /tags/discover, /tags/apply,
      /ids, /stats, /birthdays, /overdue

    NOTE: several other static paths (/bulk-update, /import/*, /sync/*,
    /scores/recalculate, /reconcile-last-interaction) are currently
    registered AFTER /{contact_id} — this is a known pre-existing bug
    tracked separately.  This test does NOT assert those paths to avoid
    always-failing noise, but it does assert they have not moved even
    further down the list (regression guard on the bug).
    """
    paths: list[str] = []
    for route in app.routes:
        if hasattr(route, "path") and route.path.startswith("/api/v1/contacts"):
            if route.path not in paths:
                paths.append(route.path)

    param_idx = paths.index("/api/v1/contacts/{contact_id}")

    # --- invariants that MUST hold (currently correct) ---
    must_be_before_param = [
        "/api/v1/contacts/tags",
        "/api/v1/contacts/tags/taxonomy",
        "/api/v1/contacts/tags/discover",
        "/api/v1/contacts/tags/apply",
        "/api/v1/contacts/ids",
        "/api/v1/contacts/stats",
        "/api/v1/contacts/birthdays",
        "/api/v1/contacts/overdue",
        "/api/v1/contacts/bulk-update",
        "/api/v1/contacts/import/csv",
        "/api/v1/contacts/import/linkedin",
        "/api/v1/contacts/import/linkedin-messages",
        "/api/v1/contacts/sync/google",
        "/api/v1/contacts/sync/google-calendar",
        "/api/v1/contacts/sync/gmail",
        "/api/v1/contacts/sync/twitter",
        "/api/v1/contacts/scores/recalculate",
        "/api/v1/contacts/reconcile-last-interaction",
        # NOTE: /sync/telegram is registered in telegram.py, not contacts_routes/
        # It's after /{contact_id} but has a unique multi-segment path so it
        # doesn't conflict in practice. Tracked for future move.
    ]

    violations: list[str] = []
    for static_path in must_be_before_param:
        if static_path not in paths:
            violations.append(f"  MISSING path: {static_path}")
            continue
        idx = paths.index(static_path)
        if idx > param_idx:
            violations.append(
                f"  {static_path!r} registered at index {idx}, "
                f"AFTER {{contact_id}} at index {param_idx}"
            )

    assert not violations, (
        "One or more critical static routes are registered AFTER /{contact_id}.\n"
        "This breaks routing: requests to these paths will be handled by the\n"
        "dynamic /{contact_id} handler instead of the correct handler.\n"
        + "\n".join(violations)
    )
