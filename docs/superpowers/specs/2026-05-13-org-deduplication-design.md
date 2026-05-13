# Organization Deduplication — Design

**Date:** 2026-05-13
**Status:** Approved — ready for implementation plan

## Problem

Organizations get duplicated in two ways:

1. **Case/format variations.** `auto_create_organization` matches by `ilike(company)`, which collapses case but not punctuation or suffixes. So "Anthropic", "Anthropic, Inc.", and "Anthropic PBC" become three separate org rows for the same real-world company.
2. **Cross-source variants.** A contact synced from Gmail with company "Anthropic", another from LinkedIn with "Anthropic AI", and a manual import with "Anthropic, Inc." each create their own org. None of the existing matching logic uses domain, LinkedIn URL, or website to collapse these.

There's already a `POST /api/v1/organizations/merge` endpoint that moves contacts from N source orgs to a target org and deletes the sources — but no automated detection. Users have no way to discover duplicates short of scrolling the orgs list.

Goal: ship a detect-and-merge flow for orgs that mirrors the existing contact `/identity` flow — same UX, same auto-merge-deterministic / queue-fuzzy pattern.

## Non-Goals

- Cross-user org consolidation. Single-player; scans are scoped to a user's own orgs.
- Hierarchy detection (parent companies, subsidiaries). If two orgs look like the same company, they merge; "Alphabet" and "Google" as separate entities is fine as long as they have different signals.
- Automated continuous detection on every contact create. The `auto_create_organization` write path stays as-is. Detection runs on user-initiated scan only.
- Domain-based blocking for users with 1000+ orgs. Out of scope for v1; O(n²) is fine up to ~500 orgs.

## Decisions Locked In

| Decision | Choice |
|---|---|
| Trigger | User-initiated "Scan for duplicates" button on `/identity?tab=orgs` |
| Detection tiers | Tier 1 deterministic (auto-merge) + Tier 2 probabilistic (queue for review) |
| Auto-merge | Same non-generic domain OR same LinkedIn URL OR (same normalized name AND same website); plus probabilistic score ≥ 0.95 |
| Review threshold | Probabilistic score 0.40–0.95 lands in `org_identity_matches` |
| Scoring shape | Name-heavy: name 40%, domain 20%, linkedin 20%, website 10%, twitter 10%; adaptive-weight redistribution like contact scorer |
| UI location | `/identity` page with a Contacts \| Orgs tab toggle |
| Storage | New `org_identity_matches` table (mirrors `identity_matches` structure) |
| Component reuse | Refactor existing `MatchCard` into a generic `MatchCardShell` + thin wrappers per entity type |

## Architecture

```
┌─────────────────────────────────────┐         ┌──────────────────────────────┐
│ User clicks "Scan for duplicates"   │         │ User opens /identity?tab=orgs│
│ on /identity?tab=orgs               │         └────────────────┬─────────────┘
└────────────────┬────────────────────┘                          │
                 ▼                                               ▼
   POST /api/v1/organizations/scan-duplicates    GET /api/v1/organizations/duplicates
                 │                                               │
                 ▼                                               │
   org_identity_resolution.find_org_matches                      │
                 │                                               │
   ┌─────────────┴───────────────────────────────┐               │
   │                                             │               │
   ▼                                             ▼               │
Tier 1 deterministic            Tier 2 probabilistic             │
  same non-generic domain          compute_org_adaptive_score    │
  same linkedin_url                  ≥ 0.95 → auto-merge         │
  same name + same website           0.40-0.95 → queue           │
                 │                                               │
                 ▼                                               │
   ┌──────────────────────────────────┐                          │
   │ Auto-merged via merge_org_pair    │  pending review rows    │
   │ (shared helper — also called by   │       ▼                 │
   │  the per-pair merge endpoint)     │  org_identity_matches   │
   └──────────────────────────────────┘       ▲                 │
                                              └─────────────────┘
                                                      │
                                                      ▼
                                            <OrgMatchCard/> list
                                                      │
                       ┌──────────────────────────────┤
                       ▼                              ▼
   POST /duplicates/{id}/merge          POST /duplicates/{id}/dismiss
   { target_id }                        (status: dismissed)
   (status: merged, contacts moved)
```

## Backend

### New files

| File | Purpose |
|---|---|
| `app/models/org_identity_match.py` | SQLAlchemy model for `org_identity_matches` table |
| `alembic/versions/<rev>_add_org_identity_matches.py` | Migration creating the table + unique index |
| `app/services/org_identity_scoring.py` | Pure scoring helpers (no DB). Mirrors `identity_scoring.py`. |
| `app/services/org_identity_resolution.py` | `find_org_matches`, `find_deterministic_org_matches`, `merge_org_pair`. DB-aware. |
| `app/schemas/org_identity_match.py` | Pydantic schemas for the endpoint envelopes |
| `app/api/organizations_duplicates.py` | The 4 new endpoints |
| `tests/test_org_identity_scoring.py` | Scoring + URL normalizer tests |
| `tests/test_org_identity_resolution.py` | DB-backed scan + auto-merge tests |
| `tests/test_api_org_duplicates.py` | Endpoint tests |

### Modified files

- `app/api/contacts.py` — no change (router file)
- `app/main.py` — register the new router (`from app.api.organizations_duplicates import router as org_duplicates_router; app.include_router(org_duplicates_router)`)
- `docs/docs/api-reference.md` — add the 4 new routes under the Organizations section
- `backend/openapi.json` + `frontend/src/lib/api-types.d.ts` — regenerated

### `OrgIdentityMatch` model

```python
class OrgIdentityMatch(Base):
    __tablename__ = "org_identity_matches"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    org_a_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    org_b_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    # "deterministic_domain" | "deterministic_linkedin" | "deterministic_name_website" | "probabilistic"
    match_method: Mapped[str] = mapped_column(String, nullable=False)
    # "pending_review" | "merged" | "dismissed"
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending_review")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
```

Unique index on `(user_id, LEAST(org_a_id, org_b_id), GREATEST(org_a_id, org_b_id))` so a re-scan doesn't double-insert the same pair. Cascade delete on org removal cleans up dead match rows.

### Scoring (`org_identity_scoring.py`)

```python
def compute_org_adaptive_score(a: Organization, b: Organization) -> float:
    """Mirror of _compute_adaptive_score for contacts, with org signals."""
    BASE_WEIGHTS = {
        "name":     0.40,
        "domain":   0.20,
        "linkedin": 0.20,
        "website":  0.10,
        "twitter":  0.10,
    }
    ...
```

Reuses from `app/services/identity_scoring.py`:
- `_name_similarity` (Levenshtein-based, with first/last-token guards)
- `_username_similarity` (for twitter handles)

New helpers:
- `_normalize_linkedin_url(url)` — strips protocol, `www.`, trailing slash, normalizes `/company/X/` vs `/company/X`. Returns `None` for unparseable.
- `_normalize_website(url)` — strips protocol, `www.`, trailing slash, path beyond the host.
- `_same_non_generic_domain(a, b)` — uses the same generic-provider set already in `_email_domain_match`. Returns `True` only if both orgs have the same non-generic domain.
- `_same_linkedin(a, b)` — both normalize to the same value (and both non-empty).

**Guards (same shape as contact scorer):**
- Single-token name on either side, no corroborating signal → cap at 0.50
- `name_score < 0.5` even when domain+linkedin both match → cap at 0.50 (likely shared infrastructure, different orgs — e.g., two consulting subsidiaries on the same parent's domain)
- Only one signal active and it's name → cap at 0.70 (force manual review)

### Deterministic matching

```python
async def find_deterministic_org_matches(
    user_id: UUID, db: AsyncSession,
) -> list[tuple[Organization, Organization, str]]:
    """Returns (org_a, org_b, match_method) for pairs that should auto-merge."""
```

Three rules, evaluated in order. First match wins for tagging:

1. **Same non-generic domain.** SQL: `SELECT a, b FROM organizations a JOIN organizations b ON a.id < b.id AND a.user_id = b.user_id AND lower(a.domain) = lower(b.domain) WHERE a.user_id = :uid AND a.domain IS NOT NULL AND lower(a.domain) NOT IN (...generic providers)`.
2. **Same LinkedIn URL.** Same shape, on normalized linkedin_url. Done in Python after SELECT because normalization isn't a single SQL function.
3. **Same normalized name AND same normalized website.** Python-side comparison after SQL pre-filter on `lower(trim(name))`. "Normalized name" here means lowercased + whitespace-trimmed (the existing `_normalize_name` helper); "normalized website" is the `_normalize_website` helper described above (strip protocol, `www.`, trailing slash, path beyond host).

### Probabilistic matching

```python
async def find_probabilistic_org_matches(
    user_id: UUID, db: AsyncSession,
    *, exclude_ids: set[UUID],   # already-merged-this-run, skip
) -> list[tuple[Organization, Organization, float]]:
```

For users with up to ~500 orgs, O(n²) is fine: 250k pair comparisons × few microseconds per scoring call = sub-second.

Cheap pre-filter before scoring: skip pair if **none** of the following share any anchor:
- First 3 chars of normalized name
- Non-generic domain
- LinkedIn URL host+path-first-segment
- Normalized website host

A pair must share at least one anchor to be scored. Filters out >95% of pairs cheaply.

Score thresholds:
- `>= 0.95`: auto-merge (treated as Tier 1)
- `0.40 - 0.95`: insert into `org_identity_matches` with `status='pending_review'`
- `< 0.40`: ignore

### Auto-merge flow

```python
async def merge_org_pair(target: Organization, source: Organization, db: AsyncSession) -> int:
    """Move source's contacts to target, delete source, return count moved.
    
    Picks target = whichever org has more contacts; ties broken by older created_at.
    Reuses the same logic that's already in the merge_organizations endpoint.
    """
```

Existing merge endpoint logic (`update Contact.organization_id`, then delete source) is extracted into this helper so both the endpoint and the auto-merge code call it.

Logo handling: if target has no logo and source does, copy `logo_url` over before delete. Same for `website`, `linkedin_url`, `twitter_handle`, `industry`, `location`, `notes` — fill any field on target that's null using source's value. Conservative: never overwrite an existing target field.

### Endpoints (`app/api/organizations_duplicates.py`)

```
POST /api/v1/organizations/scan-duplicates
  Auth: required
  Body: {}
  Response: Envelope[ScanResult]
    ScanResult { matches_found: int, auto_merged: int, pending_review: int }
  
GET  /api/v1/organizations/duplicates
  Auth: required
  Response: Envelope[list[OrgIdentityMatchData]]
    OrgIdentityMatchData {
      id, match_score, match_method, status,
      org_a: { id, name, domain, logo_url, contact_count, linkedin_url, website, twitter_handle },
      org_b: { same shape }
    }
  
POST /api/v1/organizations/duplicates/{match_id}/merge
  Auth: required
  Body: { target_id: UUID }   # must be one of org_a_id, org_b_id
  Response: Envelope[MergeResult]
    MergeResult { merged: bool, target_id: UUID, contacts_moved: int }
  Effect: calls merge_org_pair, updates match.status='merged', resolved_at=now
  
POST /api/v1/organizations/duplicates/{match_id}/dismiss
  Auth: required
  Response: Envelope[{ dismissed: true }]
  Effect: match.status='dismissed', resolved_at=now
```

All endpoints check `user_id == current_user.id` on every org/match touched (404 on mismatch).

### Error handling

Per `.claude/rules/exception-handling.md`. Scoring errors log + return 0.0 (a single bad org doesn't kill the scan). Merge endpoint logs + rolls back the transaction on failure; status stays `pending_review` so user can retry.

## Frontend

### Strategy: refactor + reuse

Existing `MatchCard` in `frontend/src/app/identity/_components/match-card.tsx` (extracted in PR #82) is contact-specific. Generalize once:

1. Pull the outer shell (header pill, score bar, expandable breakdown, action footer) into `match-card-shell.tsx`.
2. `MatchCard` becomes a thin wrapper: passes `ContactPanel` left/right + contact-specific breakdown labels. Public API and imports unchanged — `/identity/page.tsx` continues importing `MatchCard` from the same path with the same props.
3. `OrgMatchCard` is another thin wrapper: passes `OrgPanel` + org-specific breakdown labels.

This means **zero changes outside `_components/`** for the existing contact flow.

### New files

| File | Lines (rough) | Purpose |
|---|---:|---|
| `_components/match-card-shell.tsx` | ~200 | Generic shell extracted from current MatchCard |
| `_components/org-match-card.tsx` | ~40 | Thin wrapper, passes `OrgPanel` + org breakdown |
| `_components/org-panel.tsx` | ~50 | Right/left org card: logo (CompanyFavicon), name, domain, linkedin, website, contact count |
| `hooks/use-org-identity.ts` | ~60 | `useOrgMatches`, `useScanOrgs`, `useMergeOrgMatch`, `useDismissOrgMatch` |

### Modified files

- `_components/match-card.tsx` — slim to ~50 lines wrapping `MatchCardShell`
- `app/identity/page.tsx` — add tab toggle, branch on `tab === "orgs"` to render the new view

### Tab toggle (in `identity/page.tsx`)

URL-bound: `?tab=orgs` selects the orgs view; default is contacts. ~30 lines added:

```tsx
const searchParams = useSearchParams();
const router = useRouter();
const tab: "contacts" | "orgs" = searchParams.get("tab") === "orgs" ? "orgs" : "contacts";

const setTab = (t: "contacts" | "orgs") => {
  const params = new URLSearchParams(searchParams.toString());
  if (t === "orgs") params.set("tab", "orgs"); else params.delete("tab");
  router.replace(`/identity${params.toString() ? "?" + params : ""}`);
};
```

The pill toggle UI is inline in the page (3-4 buttons styled like tab pills) — small enough to not need its own component.

### `OrgPanel`

Reuses existing components:
- `CompanyFavicon` (used in `nav-search`, contact details) for the logo
- Plain `<a>` tags for linkedin / website (no new component)
- Existing Tailwind utility classes — no new styles

Shows: logo, name, domain, linkedin URL (if set), website (if set), contact count.

### `OrgMatchCard`

Picks the "Merge into X" target by contact count (whichever org has more contacts is the suggested canonical). Both the left and right entity can be the target — user clicks the merge button on the side they want to keep. Breakdown rows match the scoring weights:

```typescript
const ORG_BREAKDOWN = [
  { label: "Name", weight: 40 },
  { label: "Domain", weight: 20 },
  { label: "LinkedIn", weight: 20 },
  { label: "Website", weight: 10 },
  { label: "Twitter", weight: 10 },
];
```

## Testing

### Backend

- `tests/test_org_identity_scoring.py` — parametrized table covering every guard, normalizer correctness, generic-domain exclusion
- `tests/test_org_identity_resolution.py` — DB-backed scan: seed N orgs, assert auto-merges happen, pending matches inserted, re-scan idempotent (no duplicate rows), dismissed pairs don't resurface
- `tests/test_api_org_duplicates.py` — 4 endpoints, auth checks, cross-user 404s, end-to-end merge moves contacts

### Frontend

- `_components/match-card-shell.test.tsx` — generic shell behavior (score pill colors, expand toggle, button wiring)
- `_components/org-match-card.test.tsx` — renders with mock match, merge button label includes target name, breakdown rows show org-specific labels
- Page-level: tab routing via `?tab=orgs` URL param

### CI guards

- `check_response_models.py` passes automatically (envelope-wrapped responses)
- `check-file-length.sh` — new files designed <500 lines; org-duplicates router stays small because it's only 4 endpoints; `organizations.py` is unaffected
- `check-as-any.sh` — no `as any` usage

## Rollout

Three PRs, each green on its own:

1. **PR 1 — Backend foundation.** Model, migration, scoring, resolution service, tests. No endpoints wired. No user-visible change.
2. **PR 2 — API + frontend refactor.** Add the 4 endpoints, register router, regen OpenAPI + API types. Extract `MatchCardShell` from `MatchCard` (no behavior change for contact `/identity` flow). API is live and testable via curl/Postman; UI doesn't expose it yet.
3. **PR 3 — Org tab + UI.** Add tab toggle, `OrgMatchCard`, `OrgPanel`, `use-org-identity.ts`. Feature is live end-to-end.

Splitting PR 1 from PR 2 lets the migration ship and bake before the API code lands. Splitting PR 2 from PR 3 lets the refactor of `MatchCard` be reviewed independently — it's the only "touchy" piece of the change.

No data backfill — pending matches are created lazily on the first user-triggered scan.

## Open Questions Resolved During Brainstorm

- **Scoring weights** — Name-heavy (mirror contact scorer) chosen over domain-heavy. Tradeoff: domain is the strongest signal for orgs and 20% weight may feel light, but the deterministic tier above catches the "shared domain = same org" case directly. Probabilistic tier is for fuzzy name variations where name should dominate.
- **Storage** — New `org_identity_matches` table (over adding `entity_type` to `identity_matches`). Cleaner schema, no nullable FKs.
- **UI location** — `/identity` page with tabs (over a new `/organizations/duplicates` route). Same conceptual flow, no need for two routes.
- **Blocking** — Skipped for v1. O(n²) up to ~500 orgs is sub-second. TODO comment in `find_probabilistic_org_matches` for future scaling.
- **Component reuse** — Refactor `MatchCard` once into a generic shell rather than copy-pasting it. Cost: touches a recently-landed file. Benefit: contact and org cards stay visually + behaviorally identical going forward, with one place to fix bugs.
