/* Christina's Health Tracker — all app logic, plain vanilla JavaScript.
   Data is stored on THIS device only, in the browser's localStorage.
   No server, no accounts. See README.md for how it all fits together. */

"use strict";

/* ============================================================
   1. CATALOG — what can be logged, grouped by category.
   Items may be a plain string, or {name, dose} where `dose`
   is the standing/target dosing shown as a reference hint.
   ============================================================ */
const CATALOG = {
  water: {
    label: "Water",
    amount: true, // ask for oz
    items: ["Light water", "Alkaline water", "Bottled water", "Other water"],
  },
  supplements: {
    label: "Supplements",
    items: [
      { name: "Cellergize (LifeWave)", dose: "stir into 8oz water each morning" },
      { name: "Transfer Factor Plus", dose: "3×/day, 1 hr before food/drink (water ok)" },
      { name: "ImmuneAdapt (A Fu Zheng)", dose: "2 caps, 3×/day" },
      { name: "Bupleurum / Liver cleanse", dose: "1 tab, 2×/day" },
      { name: "Vitamin C", dose: "AM & PM" },
      { name: "Essiac tea (organic)", dose: "2–3×/day, 2 hrs after meals, drink within 15 min" },
      { name: "Carcinosin 200c", dose: "2 pills, once a WEEK only" },
      { name: "Colostrum + Probiotic", dose: "" },
    ],
  },
  patches: {
    label: "Patches",
    location: true,
    items: ["X39", "X49", "Aeon", "Energy", "Alavida", "Glutathione",
            "Carnosine", "Nirvana", "IceWave", "SP6 Complete"],
  },
  oils: {
    label: "Oils",
    location: true,
    items: ["Past Tense", "Immortelle", "Frankincense", "Birch", "Balance", "Rose",
            "Deep Blue (oil)", "Deep Blue (lotion)", "Cleansing", "On Guard", "Valor",
            "Three Wise Men", "Citrus blend", "Tea tree", "Lemon", "Peppermint",
            "Three in one", "Breathe", "Vitamin E oil (scar)"],
  },
  lotion: {
    label: "Lotion",
    items: ["Magnesium lotion"],
  },
  weight: {
    label: "Weight",
    numeric: true, // ask for a number instead of an item
  },
};

/* Default schedule, seeded from Christina's notes (a typical day).
   She can edit/add/remove these on the Schedule screen. */
const DEFAULT_SCHEDULE = [
  { time: "06:30", label: "Wake — Light water + Cellergize water; apply oils + patches", cat: "water" },
  { time: "08:30", label: "Light water, or Immune (2) + Liver (1)", cat: "supplements" },
  { time: "09:00", label: "Immune + Liver — 1st dose", cat: "supplements" },
  { time: "09:30", label: "Water / light water", cat: "water" },
  { time: "10:30", label: "Transfer Factor (3) — 1st dose", note: "1 hr before food/other drink; take with water", cat: "supplements" },
  { time: "11:30", label: "Essiac — 1st dose", note: "2 hrs after meal; drink within 15 min", cat: "supplements" },
  { time: "12:00", label: "1st meal + water", cat: "water" },
  { time: "14:00", label: "Eat + Immune — 2nd dose", cat: "supplements" },
  { time: "16:00", label: "Snack/dinner + Liver — 2nd dose", cat: "supplements" },
  { time: "18:30", label: "Light water", cat: "water" },
  { time: "20:00", label: "Essiac — 2nd dose", note: "2 hrs after meal", cat: "supplements" },
  { time: "20:30", label: "Water, all around", cat: "water" },
  { time: "21:00", label: "Transfer Factor", cat: "supplements" },
  { time: "22:00", label: "Nighttime Cellergize + light water", note: "within 15 min", cat: "supplements" },
  { time: "23:00", label: "If still awake, Essiac", cat: "supplements" },
];

/* ============================================================
   2. STORAGE — tiny helpers over localStorage (JSON).
   ============================================================ */
const KEYS = { entries: "cht.entries", schedule: "cht.schedule", version: "cht.version" };

function load(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    console.error("Could not read", key, e);
    return fallback;
  }
}
function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    alert("Couldn't save — the phone may be low on storage. Try exporting a backup.");
    console.error(e);
  }
}

function getEntries() { return load(KEYS.entries, []); }
function setEntries(list) { save(KEYS.entries, list); }

function getSchedule() {
  let s = load(KEYS.schedule, null);
  if (!s) { s = seedSchedule(); save(KEYS.schedule, s); }
  return s;
}
function setSchedule(list) { save(KEYS.schedule, list); }

function seedSchedule() {
  return DEFAULT_SCHEDULE.map((s, i) => ({
    id: "sched-" + i + "-" + s.time.replace(":", ""),
    time: s.time, label: s.label, note: s.note || "", category: s.cat || null,
  }));
}

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

/* ============================================================
   3. DATE / TIME helpers
   ============================================================ */
function pad(n) { return String(n).padStart(2, "0"); }

// current local time as a value for <input type="datetime-local">
function nowLocalInput() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function dateKey(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
function todayKey() { return dateKey(new Date()); }

// "2026-07-04T10:45" -> Date (parsed as local time)
function parseInput(str) { return new Date(str); }

function fmtTime(date) {
  let h = date.getHours(), m = date.getMinutes();
  const ap = h < 12 ? "AM" : "PM";
  h = h % 12 || 12;
  return `${h}:${pad(m)} ${ap}`;
}
function fmtDateLong(date) {
  return date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}
// "HH:MM" -> minutes since midnight
function timeToMinutes(t) { const [h, m] = t.split(":").map(Number); return h * 60 + m; }

/* ============================================================
   4. VIEW ROUTING
   ============================================================ */
const VIEWS = ["today", "log", "history", "schedule", "settings"];
const TITLES = { today: "Today", log: "Log", history: "History", schedule: "Schedule", settings: "More" };

function show(view) {
  VIEWS.forEach(v => { document.getElementById("view-" + v).hidden = (v !== view); });
  document.getElementById("screen-title").textContent = TITLES[view];
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.view === view));
  if (view === "today") renderToday();
  if (view === "log") renderCategoryButtons();
  if (view === "history") renderHistory();
  if (view === "schedule") renderSchedule();
}

document.querySelectorAll(".tab").forEach(tab =>
  tab.addEventListener("click", () => show(tab.dataset.view)));

/* ============================================================
   5. QUICK LOG — category buttons
   ============================================================ */
function renderCategoryButtons() {
  const wrap = document.getElementById("category-buttons");
  wrap.innerHTML = "";
  Object.keys(CATALOG).forEach(cat => {
    const btn = document.createElement("button");
    btn.className = "cat-btn";
    btn.textContent = CATALOG[cat].label;
    btn.addEventListener("click", () => openEntryDialog({ category: cat }));
    wrap.appendChild(btn);
  });
}

/* ============================================================
   6. ENTRY DIALOG — create / edit / delete a logged (actual) entry
   ============================================================ */
const entryDialog = document.getElementById("entry-dialog");
let editingId = null;      // entry id when editing, else null
let dialogCategory = null; // current category in the dialog
let dialogScheduleId = null;

function openEntryDialog(opts) {
  // opts: {category, entry?, scheduleId?, presetItem?}
  const cat = opts.category;
  dialogCategory = cat;
  const conf = CATALOG[cat];
  const entry = opts.entry || null;
  editingId = entry ? entry.id : null;
  dialogScheduleId = opts.scheduleId || (entry && entry.scheduleId) || null;

  document.getElementById("entry-dialog-title").textContent =
    (entry ? "Edit — " : "Log — ") + conf.label;

  // Item picker (hidden for weight)
  const itemSel = document.getElementById("f-item");
  const itemField = itemSel.closest(".field");
  if (conf.numeric) {
    itemField.hidden = true;
  } else {
    itemField.hidden = false;
    itemSel.innerHTML = "";
    conf.items.forEach(it => {
      const name = typeof it === "string" ? it : it.name;
      const dose = typeof it === "string" ? "" : it.dose;
      const o = document.createElement("option");
      o.value = name;
      o.textContent = dose ? `${name} — ${dose}` : name;
      itemSel.appendChild(o);
    });
    const preset = opts.presetItem || (entry && entry.item);
    if (preset) itemSel.value = preset;
  }

  // Conditional fields
  toggleField("field-amount", !!conf.amount);
  toggleField("field-weight", !!conf.numeric);
  toggleField("field-location", !!conf.location);

  document.getElementById("f-amount").value = entry && entry.amount != null && conf.amount ? entry.amount : "";
  document.getElementById("f-weight").value = entry && entry.amount != null && conf.numeric ? entry.amount : "";
  document.getElementById("f-location").value = (entry && entry.location) || "";
  document.getElementById("f-notes").value = (entry && entry.notes) || "";
  document.getElementById("f-time").value = (entry && entry.timestamp) || nowLocalInput();

  document.getElementById("entry-delete").hidden = !entry;
  entryDialog.showModal();
}

function toggleField(id, on) { document.getElementById(id).hidden = !on; }

document.getElementById("entry-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const conf = CATALOG[dialogCategory];
  const entries = getEntries();

  const record = {
    id: editingId || uid(),
    category: dialogCategory,
    item: conf.numeric ? "Weight" : document.getElementById("f-item").value,
    timestamp: document.getElementById("f-time").value,
    amount: null,
    location: conf.location ? (document.getElementById("f-location").value.trim() || null) : null,
    notes: document.getElementById("f-notes").value.trim(),
    scheduleId: dialogScheduleId || null,
  };
  if (conf.amount) {
    const v = document.getElementById("f-amount").value;
    record.amount = v === "" ? null : Number(v);
  }
  if (conf.numeric) {
    const v = document.getElementById("f-weight").value;
    record.amount = v === "" ? null : Number(v);
  }

  if (editingId) {
    const i = entries.findIndex(x => x.id === editingId);
    if (i >= 0) entries[i] = record;
  } else {
    entries.push(record);
  }
  setEntries(entries);
  entryDialog.close();
  refreshCurrentView();
});

document.getElementById("entry-cancel").addEventListener("click", () => entryDialog.close());
document.getElementById("entry-delete").addEventListener("click", () => {
  if (!editingId) return;
  if (!confirm("Delete this entry?")) return;
  setEntries(getEntries().filter(x => x.id !== editingId));
  entryDialog.close();
  refreshCurrentView();
});

/* ============================================================
   7. TODAY — schedule (with actual-vs-scheduled) + ad hoc entries
   ============================================================ */
function renderToday() {
  const now = new Date();
  document.getElementById("today-date").textContent = fmtDateLong(now);

  const schedule = getSchedule().slice().sort((a, b) => timeToMinutes(a.time) - timeToMinutes(b.time));
  const entries = getEntries();
  const tKey = todayKey();
  const todaysEntries = entries.filter(e => e.timestamp && e.timestamp.slice(0, 10) === tKey);

  const list = document.getElementById("today-list");
  list.innerHTML = "";

  // Scheduled items
  schedule.forEach(s => {
    // earliest actual entry today linked to this schedule item
    const done = todaysEntries
      .filter(e => e.scheduleId === s.id)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp))[0];

    const card = document.createElement("div");
    card.className = "card";

    const time = document.createElement("div");
    time.className = "sched-time";
    time.textContent = to12h(s.time);

    const main = document.createElement("div");
    main.className = "main";
    main.innerHTML = `<div class="title">${escapeHtml(s.label)}</div>` +
      (s.note ? `<div class="sub">${escapeHtml(s.note)}</div>` : "");

    card.appendChild(time);
    card.appendChild(main);

    if (done) {
      const actual = parseInput(done.timestamp);
      const diff = (actual.getHours() * 60 + actual.getMinutes()) - timeToMinutes(s.time);
      const pill = document.createElement("span");
      pill.className = "pill " + (Math.abs(diff) <= 10 ? "done" : diff < 0 ? "early" : "late");
      pill.textContent = fmtTime(actual) + diffLabel(diff);
      pill.title = "Tap to edit";
      pill.style.cursor = "pointer";
      pill.addEventListener("click", () => openEntryDialog({ category: done.category, entry: done }));
      card.appendChild(pill);
    } else {
      const btn = document.createElement("button");
      btn.className = "log-btn";
      btn.textContent = "Log";
      btn.addEventListener("click", () =>
        openEntryDialog({ category: s.category || "supplements", scheduleId: s.id, presetItem: null }));
      card.appendChild(btn);
    }
    list.appendChild(card);
  });

  // Ad hoc (not tied to a schedule item)
  const adhoc = todaysEntries.filter(e => !e.scheduleId)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  if (adhoc.length) {
    const h = document.createElement("div");
    h.className = "adhoc-heading";
    h.textContent = "Also logged today";
    list.appendChild(h);
    adhoc.forEach(e => list.appendChild(entryCard(e)));
  }

  if (!schedule.length && !todaysEntries.length) {
    list.innerHTML = `<div class="empty">Nothing yet today. Tap ＋ Log to add something.</div>`;
  }
}

function diffLabel(diff) {
  if (Math.abs(diff) <= 10) return " · on time";
  const sign = diff < 0 ? "−" : "+";
  const mins = Math.abs(diff);
  const txt = mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins} min`;
  return ` · ${sign}${txt} ${diff < 0 ? "early" : "late"}`;
}
function to12h(t) {
  const [h, m] = t.split(":").map(Number);
  const ap = h < 12 ? "AM" : "PM";
  return `${h % 12 || 12}:${pad(m)} ${ap}`;
}

/* ============================================================
   8. HISTORY — every entry, newest first, tap to edit
   ============================================================ */
function renderHistory() {
  const list = document.getElementById("history-list");
  const entries = getEntries().slice().sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  list.innerHTML = "";
  if (!entries.length) {
    list.innerHTML = `<div class="empty">No entries logged yet.</div>`;
    return;
  }
  let lastDay = null;
  entries.forEach(e => {
    const day = e.timestamp.slice(0, 10);
    if (day !== lastDay) {
      lastDay = day;
      const h = document.createElement("div");
      h.className = "adhoc-heading";
      h.textContent = fmtDateLong(parseInput(e.timestamp));
      list.appendChild(h);
    }
    list.appendChild(entryCard(e));
  });
}

// a card showing one logged entry (used in History + Today ad hoc)
function entryCard(e) {
  const card = document.createElement("div");
  card.className = "card";
  const d = parseInput(e.timestamp);

  const time = document.createElement("div");
  time.className = "sched-time";
  time.textContent = fmtTime(d);

  const main = document.createElement("div");
  main.className = "main";
  const catLabel = CATALOG[e.category] ? CATALOG[e.category].label : e.category;
  let sub = catLabel;
  if (e.amount != null) sub += e.category === "weight" ? ` · ${e.amount}` : ` · ${e.amount} oz`;
  if (e.location) sub += ` · ${e.location}`;
  main.innerHTML = `<div class="title">${escapeHtml(e.item)}</div>` +
    `<div class="sub">${escapeHtml(sub)}</div>` +
    (e.notes ? `<div class="notes">${escapeHtml(e.notes)}</div>` : "");

  card.appendChild(time);
  card.appendChild(main);
  card.style.cursor = "pointer";
  card.addEventListener("click", () => openEntryDialog({ category: e.category, entry: e }));
  return card;
}

/* ============================================================
   9. SCHEDULE editor
   ============================================================ */
const schedDialog = document.getElementById("sched-dialog");
let editingSchedId = null;

function renderSchedule() {
  const list = document.getElementById("schedule-list");
  const schedule = getSchedule().slice().sort((a, b) => timeToMinutes(a.time) - timeToMinutes(b.time));
  list.innerHTML = "";
  schedule.forEach(s => {
    const card = document.createElement("div");
    card.className = "card sched-row";
    card.innerHTML =
      `<div class="sched-time">${to12h(s.time)}</div>` +
      `<div class="main"><div class="title">${escapeHtml(s.label)}</div>` +
      (s.note ? `<div class="sub">${escapeHtml(s.note)}</div>` : "") + `</div>`;
    card.addEventListener("click", () => openSchedDialog(s));
    list.appendChild(card);
  });
}

function openSchedDialog(item) {
  editingSchedId = item ? item.id : null;
  document.getElementById("sched-dialog-title").textContent = item ? "Edit scheduled item" : "New scheduled item";
  document.getElementById("s-time").value = item ? item.time : "08:00";
  document.getElementById("s-label").value = item ? item.label : "";
  document.getElementById("s-note").value = item ? item.note : "";
  document.getElementById("sched-delete").hidden = !item;
  schedDialog.showModal();
}

document.getElementById("add-schedule-btn").addEventListener("click", () => openSchedDialog(null));
document.getElementById("reset-schedule-btn").addEventListener("click", () => {
  if (!confirm("Reset the schedule back to the default from Christina's notes? Your edits to the schedule will be replaced. (Logged entries are NOT affected.)")) return;
  setSchedule(seedSchedule());
  renderSchedule();
});

document.getElementById("sched-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const schedule = getSchedule();
  const rec = {
    id: editingSchedId || ("sched-" + uid()),
    time: document.getElementById("s-time").value,
    label: document.getElementById("s-label").value.trim(),
    note: document.getElementById("s-note").value.trim(),
    category: null,
  };
  if (editingSchedId) {
    const i = schedule.findIndex(x => x.id === editingSchedId);
    if (i >= 0) rec.category = schedule[i].category, schedule[i] = rec;
  } else {
    schedule.push(rec);
  }
  setSchedule(schedule);
  schedDialog.close();
  renderSchedule();
});
document.getElementById("sched-cancel").addEventListener("click", () => schedDialog.close());
document.getElementById("sched-delete").addEventListener("click", () => {
  if (!editingSchedId) return;
  if (!confirm("Delete this scheduled item?")) return;
  setSchedule(getSchedule().filter(x => x.id !== editingSchedId));
  schedDialog.close();
  renderSchedule();
});

/* ============================================================
   10. EXPORT / IMPORT backup
   ============================================================ */
document.getElementById("export-btn").addEventListener("click", () => {
  const data = {
    app: "christinas-health-tracker",
    version: 1,
    exportedAt: new Date().toISOString(),
    entries: getEntries(),
    schedule: getSchedule(),
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `health-tracker-backup-${todayKey()}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

document.getElementById("import-input").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!Array.isArray(data.entries)) throw new Error("no entries");
      if (!confirm(`Restore ${data.entries.length} entries from this backup? This REPLACES what's currently on the phone.`)) return;
      setEntries(data.entries);
      if (Array.isArray(data.schedule)) setSchedule(data.schedule);
      alert("Restored.");
      show("today");
    } catch (err) {
      alert("That file didn't look like a valid backup.");
      console.error(err);
    } finally {
      e.target.value = "";
    }
  };
  reader.readAsText(file);
});

/* ============================================================
   11. misc
   ============================================================ */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function refreshCurrentView() {
  const active = document.querySelector(".tab.active");
  show(active ? active.dataset.view : "today");
}

// Register the service worker for offline use (added in the PWA step).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}

// Start on Today
show("today");
