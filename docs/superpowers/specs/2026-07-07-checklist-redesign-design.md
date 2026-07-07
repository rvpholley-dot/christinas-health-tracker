# Health Tracker v2 — Checklist Redesign (Design Spec)

**Date:** 2026-07-07
**Approach:** Full rewrite of the logging flow ("Approach B"), keeping v1's visual style,
storage model, and supporting features. v1 is preserved on the `v1-backup` branch.

## Goal and why

Christina found v1's logging impractical: a red "overdue" banner she couldn't dismiss,
and a form-based dialog that made her log each thing separately with manual detail.
v2 makes the daily flow **tap → big green check mark → done**, with the time captured
automatically and editable afterward. The absence of a check mark replaces the word
"overdue."

## Requirements (agreed with Brian)

1. **One bar per item** on the Today screen. Combined slots like
   "Wake — Light water + Cellergize; apply oils + patches" become separate bars
   (Light water / Cellergize / Patches / Oils), each with its own scheduled time.
2. **Tap to check off.** Tapping an unchecked bar logs it instantly at the current
   time and shows a **large green ✓**. No dialog in the happy path.
3. **Editable timestamp.** Tapping a checked bar opens a small box: change the
   logged time, or **Un-check** (removes the entry, for accidental taps).
   For checked group bars (Patches/Oils) the same box also shows the pick-list
   so she can add/remove items from that check-off.
4. **No overdue styling anywhere.** No banner, no red pill, no "overdue" text.
   Unchecked bars look identical all day; the missing green ✓ is the signal.
5. **Patches and Oils are group bars.** Tapping opens a multi-select pick-list of
   that category's items; she selects everything applied at that one time, taps
   **Done**, and the bar gets ONE check mark with the selected items listed.
6. **Water ounces are dropped entirely.** Water is check-off only.
7. **Meals are not tracked.** (Meal mentions may remain as note text on a bar.)
8. **Ad-hoc logging** via a single "＋ Log something else" bar at the bottom of
   Today: pick category → item(s) → checked off at the current time. Weight
   prompts for the number (numeric entry; a bare check mark can't capture weight).
9. **"Add a new one…"** stays available in item pickers (custom items per
   category, persisted as in v1).

## What is removed from v1

- The **Log tab** and its category-buttons screen.
- The full entry form dialog (item dropdown + amount + location + notes + time)
  as the primary logging path. Location and per-entry notes fields go away.
- The overdue banner, overdue pill, and overdue counting logic.
- The water `amount` (oz) field and its input.

## What stays the same

- Plain HTML/CSS/JS, no build step, no server; data in `localStorage` only.
- History tab (newest-first, grouped by day; tap an entry to edit its time or
  un-check it). Grouped entries render as one line, e.g. "Patches — X39, Aeon."
- Schedule tab (add / edit / delete / re-time bars), now with a category + item
  picker per bar so new bars fit the per-item model.
- Backup export/restore (JSON), iPhone Calendar (.ics) reminders, service-worker
  offline install, welcome popup, light/dark styling, large tap targets.

## Data model

- **Entries** (`cht.entries`): `{ id, category, items: [name, ...], timestamp,
  amount (weight only), scheduleId | null }`. v1 entries (single `item` string,
  possible `amount`/`location`/`notes`) remain readable in History: display code
  accepts both shapes (`items` array or legacy `item`). No destructive migration
  of entries.
- **Schedule** (`cht.schedule`): `{ id, time, category, item | group: true,
  note }` — one item per row, except Patches/Oils rows which are category-group
  rows (multi-select on tap). The schedule is **re-seeded** to the new per-item
  default on first run of v2 (a one-time version check, `cht.version`).
  **Known trade-off:** custom schedule edits made in v1 are lost and must be
  re-entered on the Schedule tab. Logged history is untouched.
- **Custom items** (`cht.customItems`): unchanged.

## New default schedule (one bar per item)

| Time | Bar |
|------|-----|
| 6:30 | Light water |
| 6:30 | Cellergize |
| 6:30 | Patches (multi-select) |
| 6:30 | Oils (multi-select) |
| 8:30 | Light water |
| 9:00 | ImmuneAdapt |
| 9:00 | Bupleurum / Liver cleanse |
| 9:30 | Water |
| 10:30 | Transfer Factor Plus |
| 11:30 | Essiac tea |
| 12:00 | Water — note: with 1st meal |
| 14:00 | ImmuneAdapt |
| 16:00 | Bupleurum / Liver cleanse |
| 18:30 | Light water |
| 20:00 | Essiac tea — note: 2 hrs after meal |
| 20:30 | Water |
| 21:00 | Transfer Factor Plus |
| 22:00 | Cellergize — note: nighttime, within 15 min |
| 23:00 | Essiac tea — note: if still awake |

Dose reference hints from the catalog (e.g. "1 hr before food") show as small
sub-text on the bar, as v1 did with notes.

## Today screen layout

- Header: date + progress line ("7 of 15 done"). No banner.
- Bars sorted by scheduled time. Each bar: scheduled time (left), item name and
  optional note (middle), large empty circle → large green ✓ (right). When
  checked, the actual logged time shows beneath the ✓ (e.g. "✓ 9:12 AM").
- Ad-hoc entries logged today (via ＋) appear in an "Also logged today" section,
  same as v1.
- Bottom: "＋ Log something else" bar.

## Error handling

- Accidental tap → tap again → "Un-check" in the small edit box.
- Multi-select with nothing selected → Done does nothing (stays open, no error).
- Weight prompt with empty/non-numeric input → not saved, gentle message.
- `localStorage` failures keep v1's alert ("try exporting a backup").

## Testing / verification

- No test framework (plain static app, none in v1). Verification is manual,
  per the repo's build rules ("actually run it and show me the output"):
  serve locally, exercise every flow (check, un-check, edit time, multi-select
  patches, ad-hoc log, weight, history with old v1 data present, schedule edit,
  backup export/restore), in light and dark mode, at iPhone viewport width.
- Bump `CACHE_VERSION` in `service-worker.js` so installed phones update.

## Deploy plan

1. Create branch `v1-backup` at the current commit; push it to GitHub.
2. Build v2 on `main`, commit, push.
3. Verify the GitHub Pages site serves v2; open on Christina's iPhone (Safari)
   and confirm the home-screen app updates.
4. Rollback path if needed: `git checkout v1-backup` → push to `main`.
