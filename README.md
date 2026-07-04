# Christina's Health Tracker

A simple, private daily health tracker — a web app Christina saves to her iPhone
home screen. She logs the **actual** time she does each thing (water, supplements,
patches, oils, lotion, weight), and the app compares it against an **editable
schedule** so she can see how the real day lined up with the plan.

- **No accounts, no server.** All data is stored **only on the phone** (browser
  `localStorage`).
- **Works offline** once installed (service worker caches the app).
- **Plain HTML/CSS/JavaScript** — no build step, no dependencies.

## Files

| File | What it is |
|------|------------|
| `index.html` | The whole screen layout (all views live here, shown/hidden by JS). |
| `styles.css` | Styling — large tap targets, readable text, light & dark. |
| `app.js` | All the logic: categories, logging, history, schedule, comparison, backup. |
| `manifest.json` | Makes it installable as an app. |
| `service-worker.js` | Offline caching. |
| `icons/` | App icons. |

## Run it locally (on the computer)

Because of the service worker, open it through a tiny local web server rather than
double-clicking the file:

```
cd "Christina's Health Tracker"
python3 -m http.server 8000
```

Then open <http://localhost:8000> in a browser.
(Double-clicking `index.html` also mostly works, but the offline/service-worker
part only runs from a server or from the live site.)

## Put it on Christina's iPhone

1. Open the live site URL (GitHub Pages) in **Safari** — this only works in Safari,
   not Chrome, on iOS.
2. Tap the **Share** button → **Add to Home Screen**.
3. It now opens full-screen like a normal app.

## Reminders (via the iPhone's own Calendar)

Because a home-screen web app can't reliably send its own push notifications on
iPhone (Apple requires a server for that, which this app deliberately doesn't
have), reminders work by handing the schedule to the phone's Calendar:

- On the **Schedule** screen (or **More**), tap **"📅 Add my schedule to iPhone
  Calendar."** This downloads a `.ics` file; open it and choose **Add All**.
- Each scheduled time becomes a **daily repeating event with an alarm**, so
  **iOS itself** reminds her at each time — even when this app is closed.
- After editing the schedule, tap the button again to add the updated times.

The app also shows a gentle **"overdue" nudge** on the Today screen while it's
open (items whose scheduled time has passed but aren't logged yet).

## Backing up (important)

Data lives only on the phone, so a lost or wiped phone loses it. In the app go to
**More → Export a backup file** every so often and save/email/AirDrop that file to
yourself. To restore, use **More → Restore from a backup file**.

> iOS may clear a web app's stored data if the app goes unused for a long time.
> Exporting a backup now and then is the safety net.

## For the developer

- Edit `app.js` / `styles.css` / `index.html` directly — no build.
- **After changing any file, bump `CACHE_VERSION` in `service-worker.js`** (e.g.
  `cht-v1` → `cht-v2`) so installed phones pick up the new version.
- The logging categories and items live in the `CATALOG` object at the top of
  `app.js`. The default schedule is `DEFAULT_SCHEDULE` just below it.

_Personal tracking tool — not medical advice._
