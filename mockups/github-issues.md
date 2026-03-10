# GitHub Issues to Create

Once `gh auth login` is completed, create these issues:

---

## 1. Contact photo/avatar upload

**Labels:** enhancement, frontend, backend

Allow users to upload a profile photo for contacts instead of showing initials-only placeholders.

- Add file upload UI to contact detail header (click on avatar circle)
- Backend endpoint to accept image upload (resize/crop to square)
- Store in object storage, serve via CDN or static path
- Fallback to initials when no photo is set

---

## 2. Account/profile management

**Labels:** enhancement, settings

Add account management section to Settings page:

- Edit display name and email
- Change password
- Profile photo upload for the logged-in user
- Timezone / locale preferences

---

## 3. Danger zone in Settings

**Labels:** enhancement, settings

Add a "Danger Zone" section at the bottom of Settings:

- Delete account (with confirmation modal and password re-entry)
- Export all data (contacts, interactions, notes as JSON/CSV archive)

---

## 4. Import history/log

**Labels:** enhancement, settings

Show a history of past CSV imports in Settings:

- Date, filename, row count, success/error counts
- Ability to view error details per import
- Option to undo/rollback a recent import

---

## 5. Sync-now visualization

**Labels:** enhancement, settings

Add sync status and manual trigger to connected accounts:

- "Last synced" timestamp per platform (Gmail, Telegram, Twitter)
- "Sync now" button to trigger manual sync
- Progress indicator while sync is running
- Show sync errors/warnings if any
