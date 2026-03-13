# Fix Telegram Rate Limiting (Issue #27)

Created: 2026-03-13
Completed: 2026-03-13

---

## Phase 1: Use cached user IDs instead of username resolution

| Task | Description | DoD | Depends | Status |
|------|-------------|-----|---------|--------|
| 1.1 | `sync_telegram_bios()` — use `contact.telegram_user_id` (numeric) before falling back to username in `get_input_entity` call | Bio sync resolves by ID when available; username only used as fallback | - | cc:完了 |
| 1.2 | `fetch_common_groups()` — flip preference: use `telegram_user_id` first, `telegram_username` second | Common groups resolved by ID when available | - | cc:完了 |

---

## Phase 2: Add inter-call delays and sequential sync

| Task | Description | DoD | Depends | Status |
|------|-------------|-----|---------|--------|
| 2.1 | Add `asyncio.sleep(random.uniform(0.5, 1.0))` between iterations in `sync_telegram_bios()` contact loop | Each bio fetch separated by 0.5-1s random delay | 1.1 | cc:完了 |
| 2.2 | Add `asyncio.sleep(random.uniform(0.5, 1.0))` between iterations in `sync_telegram_chats()` dialog message-fetch loop | Each dialog's message fetch separated by 0.5-1s random delay | - | cc:完了 |
| 2.3 | Add `asyncio.sleep(random.uniform(0.5, 1.0))` between iterations in `sync_telegram_group_members()` group loop | Each group's participant fetch separated by 0.5-1s random delay | - | cc:完了 |
| 2.4 | Change `sync_telegram_for_user()` from Celery chord (parallel) to chain (sequential): chats → groups → bios | `sync_telegram_for_user` uses `chain()` instead of `chord()` | - | cc:完了 |

---

## Phase 3: Surface rate limit to UI

| Task | Description | DoD | Depends | Status |
|------|-------------|-----|---------|--------|
| 3.1 | When `FloodWaitError` is caught, create a Notification with `notification_type="system"` so it appears in the System tab at `/notifications`. Title: "Telegram rate limit", body includes wait duration. | Notification with type `system` created and visible in System tab | Phase 1 | cc:完了 |

---

## Notes

- **Root cause:** `sync_telegram_bios()` calls `get_input_entity(username)` for up to 100 contacts without using cached `telegram_user_id`, triggering rate-limited `ResolveUsernameRequest` on every call
- **Bio sync scope:** Deferred to GH Issue #29 for separate decision
- **Related:** GH Issue #27
