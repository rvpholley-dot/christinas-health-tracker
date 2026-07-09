# Pull sync: agent entries into the phone app — design

**Date:** 2026-07-09
**Status:** Approved by Brian (this session)
**Problem:** The v3 sync is push-only. Entries the Telegram bot logs reach the
shared ledger and the app's Log tab, but never the phone's local state — so
they don't check off Today bars, don't appear in History, and Christina can't
edit them in the app. She wants bot-logged items to behave exactly as if she
tapped them herself.

## Goals

- Bot-logged entries check off the matching Today bar, with the time she said.
- Bot edits and deletions flow down too (full two-way), possibly un-checking
  a bar.
- Her own in-app actions always win over stale server state for entries she
  is editing.
- Offline behavior unchanged: the phone keeps working with no tailnet; pull
  failures are silent.

## Non-goals

- No background sync (iOS PWAs can't). Pull happens when the app opens,
  foregrounds, or regains network — the same moments push happens today.
- No `updated_at`/cursor protocol. The 7-day window of one person's entries
  is small; re-merging it is cheap and idempotent.

## Approach (chosen from three)

Piggyback on the existing authenticated `GET /log` fetch. Rejected: a
dedicated `/pull` endpoint with a `since` cursor (needs an `updated_at`
migration; scale that doesn't exist), and server-computed Today state
(breaks offline).

## Agent side (`agent/api.py`)

`GET /log` accepts `include_deleted=1`. When set, the `entries` array also
includes soft-deleted rows in the window. Every entry already carries
`source`; ensure each also carries a `deleted` boolean. `totals` are
unchanged (they already exclude deleted rows). No schema changes.

## App side (`app.js`)

New `pullFromServer()`, called right after each `flushQueue()` (push first so
her fresh taps and edits reach the ledger before the merge), on the existing
triggers: load, `visibilitychange` to visible, `online`. It fetches
`/log?days=7&include_deleted=1` itself (the Log tab keeps its existing
independent fetch) and merges into `cht.entries`:

| Server entry | Local state | Action |
|---|---|---|
| id unknown locally | — | Insert locally (any source — also gives free restore of the last 7 days if localStorage is ever wiped) |
| id known, `source !== 'app'` | id **not** in pending sync queue | Overwrite local copy with server copy (server wins for bot-owned entries, including `deleted` tombstones) |
| id known, `source !== 'app'` | id in pending sync queue | Skip — her un-pushed edit wins; it pushes up and converges next pull |
| id known, `source === 'app'` | — | Never touched; the phone is authoritative for her own entries |

Local entry shape gains an optional `source` field (absent = `'app'`).
Pulled entries are NOT enqueued by the merge itself (nothing changed to push)
— except when matching assigns a `scheduleId` (below).

### Checkmark matching

Today bars are matched strictly by `entry.scheduleId` (`app.js`
`renderToday`). Bot entries arrive with `scheduleId = null`, so after each
merge, for every non-deleted entry that lacks a `scheduleId`:

1. Candidate schedule rows: same category, and (row is a group row) or
   (row.item is in the entry's items).
2. Drop rows already satisfied that calendar day by another entry
   (by scheduleId).
3. Pick the row whose `time` is nearest the entry's time-of-day; assign
   `entry.scheduleId = row.id` and `enqueueSync([entry.id])` so the ledger
   and the reminder loop learn the assignment.
4. No candidate → entry stays ad hoc ("Also logged today" / History).

Matching runs for every day in the pulled window (History benefits too), one
entry per row per day (first by timestamp).

### UI

If a merge changed anything and the current view is Today, History, or Log,
re-render it. No banners, no sync spinners — the app stays calm. Errors:
`console.warn`, silent to Christina, same as push.

## Deploy

- Bump `CACHE_VERSION` in `service-worker.js`.
- Restart cht-agent (launcher restarts on process kill).
- Commit and push to GitHub Pages (required for her phone to receive it);
  Brian confirms the push.

## Testing

- Python test: `/log?include_deleted=1` returns tombstones; default call
  doesn't.
- Browser test on localhost with seeded localStorage: insert, server-wins,
  queue-protects, tombstone un-check, nearest-bar matching (two ImmuneAdapt
  bars), group-bar matching (patches), no-candidate → ad hoc.
- Live: bot-log an item via sandbox chat id, open the app, watch the bar
  check off.

## Risks

- Double entries when she tells the bot AND taps the app for the same dose:
  both exist; the second stays ad hoc and visible, she can delete either.
  Accepted (visible beats silent dedupe guessing wrong).
- A pulled tombstone un-checks a bar she believes done: explicitly requested
  behavior (only happens when she asked the bot to delete).
