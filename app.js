/* Christina's Health Tracker v2 — all app logic, plain vanilla JavaScript.
   Data is stored on THIS device only, in the browser's localStorage.
   No server, no accounts. See README.md for how it all fits together.

   v2: the Today screen is a one-tap checklist. One bar per item; tapping a
   bar logs it at the current time and shows a green check. Patches/Oils are
   "group" bars that open a multi-select. There is no overdue styling — an
   unchecked circle next to a passed time is the only signal. */

"use strict";

/* ============================================================
   1. CATALOG — what can be logged, grouped by category.
   `group: true` categories (Patches, Oils) are logged as one
   multi-select check-off. `numeric` (Weight) asks for a number.
   ============================================================ */
const CATALOG = {
  water: {
    label: "Water",
    items: ["Light water", "Alkaline water", "Bottled water", "Other water"],
  },
  supplements: {
    label: "Supplements",
    items: [
      { name: "Cellergize (LifeWave)", dose: "stir into 8oz water" },
      { name: "Transfer Factor Plus", dose: "1 hr before food/drink (water ok)" },
      { name: "ImmuneAdapt (A Fu Zheng)", dose: "2 caps, 3×/day" },
      { name: "Bupleurum / Liver cleanse", dose: "1 tab, 2×/day" },
      { name: "Vitamin C", dose: "AM & PM" },
      { name: "Essiac tea (organic)", dose: "2 hrs after meals, drink within 15 min" },
      { name: "Carcinosin 200c", dose: "2 pills, once a WEEK only" },
      { name: "Colostrum + Probiotic", dose: "" },
    ],
  },
  patches: {
    label: "Patches",
    group: true,
    items: ["X39", "X49", "Aeon", "Energy", "Alavida", "Glutathione",
            "Carnosine", "Nirvana", "IceWave", "SP6 Complete"],
  },
  oils: {
    label: "Oils",
    group: true,
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
    numeric: true,
  },
};

/* Default schedule — ONE ITEM PER ROW (v2), seeded from Christina's notes.
   She can edit/add/remove these on the Schedule screen. */
const DEFAULT_SCHEDULE = [
  { time: "06:30", category: "water", item: "Light water" },
  { time: "06:30", category: "supplements", item: "Cellergize (LifeWave)", note: "stir into 8oz water" },
  { time: "06:30", category: "patches" },
  { time: "06:30", category: "oils" },
  { time: "08:30", category: "water", item: "Light water" },
  { time: "09:00", category: "supplements", item: "ImmuneAdapt (A Fu Zheng)", note: "2 caps" },
  { time: "09:00", category: "supplements", item: "Bupleurum / Liver cleanse", note: "1 tab" },
  { time: "09:30", category: "water", item: "Light water" },
  { time: "10:30", category: "supplements", item: "Transfer Factor Plus", note: "1 hr before food/drink (water ok)" },
  { time: "11:30", category: "supplements", item: "Essiac tea (organic)", note: "2 hrs after meal; drink within 15 min" },
  { time: "12:00", category: "water", item: "Light water", note: "with 1st meal" },
  { time: "14:00", category: "supplements", item: "ImmuneAdapt (A Fu Zheng)", note: "with food" },
  { time: "16:00", category: "supplements", item: "Bupleurum / Liver cleanse", note: "with snack/dinner" },
  { time: "18:30", category: "water", item: "Light water" },
  { time: "20:00", category: "supplements", item: "Essiac tea (organic)", note: "2 hrs after meal" },
  { time: "20:30", category: "water", item: "Light water" },
  { time: "21:00", category: "supplements", item: "Transfer Factor Plus" },
  { time: "22:00", category: "supplements", item: "Cellergize (LifeWave)", note: "nighttime, within 15 min" },
  { time: "23:00", category: "supplements", item: "Essiac tea (organic)", note: "if still awake" },
];

/* ============================================================
   2. STORAGE — tiny helpers over localStorage (JSON).
   ============================================================ */
const KEYS = { entries: "cht.entries", schedule: "cht.schedule", version: "cht.version" };
const APP_DATA_VERSION = 2;

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
    id: "sched2-" + i + "-" + s.time.replace(":", ""),
    time: s.time,
    category: s.category,
    item: s.item || null,
    group: !!(CATALOG[s.category] && CATALOG[s.category].group),
    note: s.note || "",
  }));
}

/* One-time v1 → v2 migration: the schedule format changed (one item per row),
   so reseed it. Logged entries are NOT touched — History reads old and new. */
function migrate() {
  const v = load(KEYS.version, 1);
  if (v < 2) {
    setSchedule(seedSchedule());
    save(KEYS.version, APP_DATA_VERSION);
  }
}

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

// Custom items she adds herself, kept per-category: { supplements: [...], ... }
function getCustomItems() { return load("cht.customItems", {}); }
function addCustomItem(cat, name) {
  const all = getCustomItems();
  const list = all[cat] || (all[cat] = []);
  const lc = name.toLowerCase();
  const inCatalog = ((CATALOG[cat] && CATALOG[cat].items) || [])
    .some(it => (typeof it === "string" ? it : it.name).toLowerCase() === lc);
  const inCustom = list.some(n => n.toLowerCase() === lc);
  if (!inCatalog && !inCustom) { list.push(name); save("cht.customItems", all); }
}
// catalog + custom item names for a category, as [{name, dose}]
function itemsFor(cat) {
  const out = ((CATALOG[cat] && CATALOG[cat].items) || [])
    .map(it => typeof it === "string" ? { name: it, dose: "" } : { name: it.name, dose: it.dose || "" });
  (getCustomItems()[cat] || []).forEach(name => {
    if (!out.some(o => o.name === name)) out.push({ name, dose: "" });
  });
  return out;
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
function to12h(t) {
  const [h, m] = t.split(":").map(Number);
  const ap = h < 12 ? "AM" : "PM";
  return `${h % 12 || 12}:${pad(m)} ${ap}`;
}

/* ============================================================
   4. ENTRY helpers — one place that understands v1 AND v2 shapes
   ============================================================ */
// entry -> array of item names (v2 has .items, v1 had .item)
function entryItems(e) {
  if (Array.isArray(e.items)) return e.items;
  return e.item ? [e.item] : [];
}
// display title for a schedule row
function rowTitle(s) {
  if (s.group) return CATALOG[s.category] ? CATALOG[s.category].label : s.category;
  return s.item || (s.label /* v1 leftover rows, just in case */) ||
         (CATALOG[s.category] ? CATALOG[s.category].label : s.category);
}

/* ============================================================
   5. VIEW ROUTING
   ============================================================ */
const VIEWS = ["today", "history", "schedule", "settings"];
const TITLES = { today: "Today", history: "History", schedule: "Schedule", settings: "More" };

function show(view) {
  VIEWS.forEach(v => { document.getElementById("view-" + v).hidden = (v !== view); });
  document.getElementById("screen-title").textContent = TITLES[view];
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.view === view));
  if (view === "today") renderToday();
  if (view === "history") renderHistory();
  if (view === "schedule") renderSchedule();
}

document.querySelectorAll(".tab").forEach(tab =>
  tab.addEventListener("click", () => show(tab.dataset.view)));

function refreshCurrentView() {
  const active = document.querySelector(".tab.active");
  show(active ? active.dataset.view : "today");
}

/* ============================================================
   6. TODAY — the checklist
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
  let doneCount = 0;

  schedule.forEach(s => {
    // earliest entry today linked to this bar
    const done = todaysEntries
      .filter(e => e.scheduleId === s.id)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp))[0];
    if (done) doneCount++;

    const card = document.createElement("div");
    card.className = "card check-row";

    const time = document.createElement("div");
    time.className = "sched-time";
    time.textContent = to12h(s.time);

    const main = document.createElement("div");
    main.className = "main";
    let subBits = [];
    if (done && s.group) subBits.push(entryItems(done).join(", "));
    if (s.note) subBits.push(s.note);
    main.innerHTML = `<div class="title">${escapeHtml(rowTitle(s))}</div>` +
      (subBits.length ? `<div class="sub">${escapeHtml(subBits.join(" · "))}</div>` : "");

    const wrap = document.createElement("div");
    wrap.className = "check-wrap";
    const check = document.createElement("div");
    check.className = "check" + (done ? " done" : "");
    check.textContent = "✓";
    wrap.appendChild(check);
    if (done) {
      const t = document.createElement("div");
      t.className = "check-time";
      t.textContent = fmtTime(parseInput(done.timestamp));
      wrap.appendChild(t);
    }

    card.appendChild(time);
    card.appendChild(main);
    card.appendChild(wrap);
    card.addEventListener("click", () => {
      if (done) { openEdit(done); }
      else if (s.group) { openPicker({ category: s.category, scheduleId: s.id }); }
      else { quickLog(s); }
    });
    list.appendChild(card);
  });

  // progress line ("7 of 15 done") — calm, no colors, no warnings
  const prog = document.getElementById("today-progress");
  if (schedule.length) {
    prog.hidden = false;
    prog.textContent = `${doneCount} of ${schedule.length} done`;
  } else {
    prog.hidden = true;
  }

  // ad hoc entries (logged via ＋, not tied to a bar)
  const adhoc = todaysEntries.filter(e => !e.scheduleId)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  if (adhoc.length) {
    const h = document.createElement("div");
    h.className = "adhoc-heading";
    h.textContent = "Also logged today";
    list.appendChild(h);
    adhoc.forEach(e => list.appendChild(entryCard(e)));
  }

  // the "＋ Log something else" bar, always last
  const addBar = document.createElement("div");
  addBar.className = "card add-row";
  addBar.textContent = "＋ Log something else";
  addBar.addEventListener("click", () => openPicker({}));
  list.appendChild(addBar);
}

// one-tap check-off for a single-item bar
function quickLog(s) {
  const entries = getEntries();
  entries.push({
    id: uid(),
    category: s.category,
    items: [s.item || rowTitle(s)],
    timestamp: nowLocalInput(),
    amount: null,
    scheduleId: s.id,
  });
  setEntries(entries);
  renderToday();
}

/* ============================================================
   7. PICKER — multi-select for group bars and "Log something else"
   ============================================================ */
const pickerDialog = document.getElementById("picker-dialog");
let pickerState = null; // { category, scheduleId }

function openPicker(opts) {
  pickerState = { category: opts.category || null, scheduleId: opts.scheduleId || null };
  const catsDiv = document.getElementById("picker-cats");
  catsDiv.hidden = !!pickerState.category;
  catsDiv.innerHTML = "";
  if (!pickerState.category) {
    document.getElementById("picker-title").textContent = "Log something else";
    Object.keys(CATALOG).forEach(cat => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "cat-btn";
      b.textContent = CATALOG[cat].label;
      b.addEventListener("click", () => { pickerState.category = cat; renderPickerBody(); catsDiv.hidden = true; });
      catsDiv.appendChild(b);
    });
    document.getElementById("picker-items").innerHTML = "";
    document.getElementById("picker-newitem-field").hidden = true;
    document.getElementById("picker-weight-field").hidden = true;
  } else {
    renderPickerBody();
  }
  document.getElementById("picker-newitem").value = "";
  document.getElementById("picker-weight").value = "";
  pickerDialog.showModal();
}

function renderPickerBody() {
  const cat = pickerState.category;
  const conf = CATALOG[cat];
  document.getElementById("picker-title").textContent = "Log — " + conf.label;
  const itemsDiv = document.getElementById("picker-items");
  itemsDiv.innerHTML = "";
  const isWeight = !!conf.numeric;
  document.getElementById("picker-weight-field").hidden = !isWeight;
  document.getElementById("picker-newitem-field").hidden = isWeight;
  if (isWeight) return;
  itemsFor(cat).forEach(it => {
    itemsDiv.appendChild(pickerRow(it.name, it.dose, false));
  });
}

// one labelled checkbox row (shared by picker and edit dialogs)
function pickerRow(name, dose, checked) {
  const label = document.createElement("label");
  label.className = "picker-item";
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.value = name;
  cb.checked = checked;
  const span = document.createElement("span");
  span.innerHTML = escapeHtml(name) + (dose ? `<span class="dose">${escapeHtml(dose)}</span>` : "");
  label.appendChild(cb);
  label.appendChild(span);
  return label;
}

document.getElementById("picker-form").addEventListener("submit", (e) => {
  e.preventDefault();
  if (!pickerState || !pickerState.category) return; // no category picked yet — stay open
  const cat = pickerState.category;
  const conf = CATALOG[cat];

  let items = [];
  let amount = null;

  if (conf.numeric) {
    const v = document.getElementById("picker-weight").value;
    const n = Number(v);
    if (v === "" || !isFinite(n) || n <= 0) { alert("Type your weight first. 💛"); return; }
    amount = n;
    items = ["Weight"];
  } else {
    items = Array.from(document.querySelectorAll("#picker-items input:checked")).map(cb => cb.value);
    const extra = document.getElementById("picker-newitem").value.trim();
    if (extra) { items.push(extra); addCustomItem(cat, extra); }
    if (!items.length) return; // nothing selected — stay open, no error
  }

  const entries = getEntries();
  entries.push({
    id: uid(),
    category: cat,
    items: items,
    timestamp: nowLocalInput(),
    amount: amount,
    scheduleId: pickerState.scheduleId,
  });
  setEntries(entries);
  pickerDialog.close();
  refreshCurrentView();
});

document.getElementById("picker-cancel").addEventListener("click", () => pickerDialog.close());

/* ============================================================
   8. EDIT — fix the time, adjust group items, or un-check
   ============================================================ */
const editDialog = document.getElementById("edit-dialog");
let editingEntryId = null;

function openEdit(entry) {
  editingEntryId = entry.id;
  const conf = CATALOG[entry.category] || {};
  document.getElementById("edit-title").textContent =
    "Edit — " + (conf.label || entry.category);

  // group categories: show the pick-list so she can add/remove items
  const itemsDiv = document.getElementById("edit-items");
  itemsDiv.innerHTML = "";
  if (conf.group) {
    const selected = entryItems(entry);
    const listed = itemsFor(entry.category);
    listed.forEach(it => {
      itemsDiv.appendChild(pickerRow(it.name, it.dose, selected.includes(it.name)));
    });
    // keep one-off/custom names that aren't in the list anymore
    selected.forEach(name => {
      if (!listed.some(it => it.name === name)) {
        itemsDiv.appendChild(pickerRow(name, "", true));
      }
    });
  }

  const isWeight = !!conf.numeric;
  document.getElementById("edit-weight-field").hidden = !isWeight;
  if (isWeight) document.getElementById("edit-weight").value = entry.amount != null ? entry.amount : "";

  document.getElementById("edit-time").value = entry.timestamp || nowLocalInput();
  editDialog.showModal();
}

document.getElementById("edit-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const entries = getEntries();
  const i = entries.findIndex(x => x.id === editingEntryId);
  if (i < 0) { editDialog.close(); return; }
  const entry = entries[i];
  const conf = CATALOG[entry.category] || {};

  if (conf.group) {
    const items = Array.from(document.querySelectorAll("#edit-items input:checked")).map(cb => cb.value);
    if (!items.length) { alert("Nothing is selected — use Un-check instead if this wasn't done."); return; }
    entry.items = items;
    delete entry.item; // upgrade any legacy single-item shape
  }
  if (conf.numeric) {
    const v = document.getElementById("edit-weight").value;
    const n = Number(v);
    if (v === "" || !isFinite(n) || n <= 0) { alert("Type your weight first. 💛"); return; }
    entry.amount = n;
  }
  entry.timestamp = document.getElementById("edit-time").value;
  entries[i] = entry;
  setEntries(entries);
  editDialog.close();
  refreshCurrentView();
});

document.getElementById("edit-uncheck").addEventListener("click", () => {
  setEntries(getEntries().filter(x => x.id !== editingEntryId));
  editDialog.close();
  refreshCurrentView();
});
document.getElementById("edit-cancel").addEventListener("click", () => editDialog.close());

/* ============================================================
   9. HISTORY — every entry, newest first, tap to edit
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
  const title = entryItems(e).join(", ") || catLabel;
  let sub = catLabel;
  if (e.category === "weight" && e.amount != null) sub += ` · ${e.amount}`;
  if (e.location) sub += ` · ${e.location}`;             // legacy v1 field
  main.innerHTML = `<div class="title">${escapeHtml(title)}</div>` +
    `<div class="sub">${escapeHtml(sub)}</div>` +
    (e.notes ? `<div class="notes">${escapeHtml(e.notes)}</div>` : ""); // legacy v1 field

  card.appendChild(time);
  card.appendChild(main);
  card.style.cursor = "pointer";
  card.addEventListener("click", () => openEdit(e));
  return card;
}

/* ============================================================
   10. SCHEDULE editor
   ============================================================ */
const schedDialog = document.getElementById("sched-dialog");
let editingSchedId = null;
const S_ADD_NEW = "__add_new__";

function renderSchedule() {
  const list = document.getElementById("schedule-list");
  const schedule = getSchedule().slice().sort((a, b) => timeToMinutes(a.time) - timeToMinutes(b.time));
  list.innerHTML = "";
  schedule.forEach(s => {
    const card = document.createElement("div");
    card.className = "card sched-row";
    card.innerHTML =
      `<div class="sched-time">${to12h(s.time)}</div>` +
      `<div class="main"><div class="title">${escapeHtml(rowTitle(s))}</div>` +
      (s.note ? `<div class="sub">${escapeHtml(s.note)}</div>` : "") + `</div>`;
    card.addEventListener("click", () => openSchedDialog(s));
    list.appendChild(card);
  });
}

function fillSchedItemSelect(cat, preset) {
  const conf = CATALOG[cat];
  const field = document.getElementById("s-item-field");
  const sel = document.getElementById("s-item");
  document.getElementById("s-newitem-field").hidden = true;
  document.getElementById("s-newitem").value = "";
  if (conf.group || conf.numeric) { field.hidden = true; return; }
  field.hidden = false;
  sel.innerHTML = "";
  itemsFor(cat).forEach(it => {
    const o = document.createElement("option");
    o.value = it.name;
    o.textContent = it.dose ? `${it.name} — ${it.dose}` : it.name;
    sel.appendChild(o);
  });
  if (preset && !Array.from(sel.options).some(o => o.value === preset)) {
    const o = document.createElement("option");
    o.value = preset; o.textContent = preset;
    sel.appendChild(o);
  }
  const add = document.createElement("option");
  add.value = S_ADD_NEW; add.textContent = "➕ Add a new one…";
  sel.appendChild(add);
  if (preset) sel.value = preset;
}

function openSchedDialog(item) {
  editingSchedId = item ? item.id : null;
  document.getElementById("sched-dialog-title").textContent = item ? "Edit scheduled item" : "New scheduled item";
  document.getElementById("s-time").value = item ? item.time : "08:00";
  document.getElementById("s-note").value = item ? (item.note || "") : "";

  const catSel = document.getElementById("s-category");
  catSel.innerHTML = "";
  Object.keys(CATALOG).filter(c => !CATALOG[c].numeric).forEach(cat => {
    const o = document.createElement("option");
    o.value = cat; o.textContent = CATALOG[cat].label;
    catSel.appendChild(o);
  });
  const cat = item ? item.category : "supplements";
  catSel.value = cat;
  fillSchedItemSelect(cat, item ? item.item : null);

  document.getElementById("sched-delete").hidden = !item;
  schedDialog.showModal();
}

document.getElementById("s-category").addEventListener("change", (e) => {
  fillSchedItemSelect(e.target.value, null);
});
document.getElementById("s-item").addEventListener("change", (e) => {
  const isNew = e.target.value === S_ADD_NEW;
  document.getElementById("s-newitem-field").hidden = !isNew;
  if (isNew) { try { document.getElementById("s-newitem").focus(); } catch (err) {} }
});

document.getElementById("add-schedule-btn").addEventListener("click", () => openSchedDialog(null));
document.getElementById("reset-schedule-btn").addEventListener("click", () => {
  if (!confirm("Reset the schedule back to the default from Christina's notes? Your edits to the schedule will be replaced. (Logged entries are NOT affected.)")) return;
  setSchedule(seedSchedule());
  renderSchedule();
});

document.getElementById("sched-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const cat = document.getElementById("s-category").value;
  const conf = CATALOG[cat];
  let itemName = null;
  if (!conf.group && !conf.numeric) {
    itemName = document.getElementById("s-item").value;
    if (itemName === S_ADD_NEW) {
      const newName = document.getElementById("s-newitem").value.trim();
      if (!newName) { alert("Type a name for the new item, or pick one from the list."); return; }
      itemName = newName;
      addCustomItem(cat, newName);
    }
  }
  const schedule = getSchedule();
  const rec = {
    id: editingSchedId || ("sched2-" + uid()),
    time: document.getElementById("s-time").value,
    category: cat,
    item: itemName,
    group: !!conf.group,
    note: document.getElementById("s-note").value.trim(),
  };
  if (editingSchedId) {
    const i = schedule.findIndex(x => x.id === editingSchedId);
    if (i >= 0) schedule[i] = rec;
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
   11. EXPORT / IMPORT backup
   ============================================================ */
document.getElementById("export-btn").addEventListener("click", () => {
  const data = {
    app: "christinas-health-tracker",
    version: 2,
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
      if (Array.isArray(data.schedule)) {
        // a v1 backup's schedule rows (label-based) don't fit the v2 checklist;
        // keep the current v2 schedule in that case, entries restore fine.
        const looksV2 = data.schedule.every(s => s.category);
        if (looksV2) setSchedule(data.schedule);
      }
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
   12. misc
   ============================================================ */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ============================================================
   13. CALENDAR REMINDERS — export the schedule as an .ics file.
   Each scheduled item becomes a daily repeating calendar event with
   an alarm, so the iPhone itself reminds her (even when this app is
   closed). No server needed — the phone's Calendar does the alerting.
   ============================================================ */
function icsEscape(s) {
  return String(s)
    .replace(/\\/g, "\\\\").replace(/;/g, "\\;")
    .replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}
// Fold long lines to <=75 octets per RFC 5545 (CRLF + leading space).
function icsFold(line) {
  const out = [];
  let s = line;
  while (s.length > 73) { out.push(s.slice(0, 73)); s = " " + s.slice(73); }
  out.push(s);
  return out.join("\r\n");
}
function icsStampUTC(d) {
  return d.getUTCFullYear() + pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) +
    "T" + pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + pad(d.getUTCSeconds()) + "Z";
}

function buildIcs() {
  const schedule = getSchedule().slice().sort((a, b) => timeToMinutes(a.time) - timeToMinutes(b.time));
  const now = new Date();
  const dateBase = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  const stamp = icsStampUTC(now);

  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0",
    "PRODID:-//Christinas Health Tracker//EN",
    "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    "X-WR-CALNAME:Health Schedule",
  ];
  schedule.forEach((s, i) => {
    const [h, m] = s.time.split(":");
    // Floating local time (no Z / no TZID) => fires at this wall-clock time.
    const dtstart = `${dateBase}T${h}${m}00`;
    const uid = `cht-${s.id}-${i}@christinas-health-tracker`;
    lines.push("BEGIN:VEVENT");
    lines.push(icsFold("UID:" + uid));
    lines.push("DTSTAMP:" + stamp);
    lines.push(icsFold("DTSTART:" + dtstart));
    lines.push("DURATION:PT10M");
    lines.push("RRULE:FREQ=DAILY");
    lines.push(icsFold("SUMMARY:" + icsEscape(rowTitle(s))));
    if (s.note) lines.push(icsFold("DESCRIPTION:" + icsEscape(s.note)));
    lines.push("BEGIN:VALARM");
    lines.push("ACTION:DISPLAY");
    lines.push(icsFold("DESCRIPTION:" + icsEscape(rowTitle(s))));
    lines.push("TRIGGER:-PT0M"); // alert at the scheduled time
    lines.push("END:VALARM");
    lines.push("END:VEVENT");
  });
  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}

function exportIcs() {
  const blob = new Blob([buildIcs()], { type: "text/calendar" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "christina-schedule.ics";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

document.querySelectorAll(".calendar-btn").forEach(b => b.addEventListener("click", exportIcs));

/* ============================================================
   14. WELCOME / how-to popup (shows on open until dismissed)
   ============================================================ */
const welcomeDialog = document.getElementById("welcome-dialog");
const WELCOME_KEY = "cht.welcomeSeen2"; // v2 key: show the new how-to once, even if v1's was dismissed

function openWelcome() {
  document.getElementById("welcome-hide").checked = false;
  welcomeDialog.showModal();
}
document.getElementById("welcome-close").addEventListener("click", () => {
  if (document.getElementById("welcome-hide").checked) {
    try { localStorage.setItem(WELCOME_KEY, "1"); } catch (e) {}
  }
  welcomeDialog.close();
});
document.getElementById("show-welcome-btn").addEventListener("click", openWelcome);

function maybeShowWelcome() {
  let seen = null;
  try { seen = localStorage.getItem(WELCOME_KEY); } catch (e) {}
  if (!seen) openWelcome();
}

// Register the service worker for offline use.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}

// Migrate v1 data (one-time schedule reseed), then start on Today
migrate();
show("today");
maybeShowWelcome();
