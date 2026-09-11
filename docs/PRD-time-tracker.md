# Time Tracker — Product Requirements Document

| | |
|---|---|
| **Document** | PRD-01 · Product requirements (technology-agnostic) |
| **Version** | 1.0 |
| **Date** | 11 September 2026 |
| **Owner** | Wouter |
| **Status** | Draft for review |
| **Companion** | `PRD-time-tracker-qt.md` — technical design & implementation plan (PySide6 / Qt 6) |

---

## 1. Summary

A tray-resident time tracker for individual professionals who bill or allocate their time across several clients. The application has no main window in the ordinary sense: it lives in the system tray / menu bar and is driven from a single popover that offers two ways to record time.

**Start–Stop mode** runs a stopwatch against a Client label and a Type-of-work label. **Add Time mode** is a clickable matrix that composes a finished entry in a handful of clicks — pick a duration, a type, a client, optionally a note, commit. Both modes write into the same chronological session log, which is stored locally in SQLite and exported on demand to CSV or XLSX.

The product bet is that time tracking fails on friction, not on features. Everything below optimises for the number of seconds between "I should log this" and "it is logged".

---

## 2. Problem

Professionals who bill by time lose revenue in two distinct ways, and they require two distinct remedies:

1. **Forgetting to start.** A block of focused work (a client call, a drafting session) begins without the stopwatch running. By the time the user remembers, the start time is a guess. → Remedy: make starting a timer a one-click, zero-decision act, and make the running state impossible to overlook.

2. **Interstitial work never gets logged at all.** Three minutes answering a client email, eight minutes on a phone call, a fifteen-minute unplanned Teams call. Individually below the threshold at which anyone bothers to start a stopwatch; collectively 20–40 % of a professional's chargeable day. → Remedy: a retroactive logger so fast that logging six minutes costs less effort than deciding whether it's worth logging.

Existing tools address (1) well and (2) badly. Toggl Track, Clockify and their peers all model the manual entry as a *form*: description field, project picker, two time fields, save. That is 20–40 seconds and a context switch. This product's second mode exists specifically to collapse that to under five seconds.

A secondary problem is **data ownership**. The dominant tools are cloud-first and account-bound. For a solo professional handling client-identifying information, a local-only tool with a plain SQLite file removes an entire class of vendor, GDPR and continuity questions.

---

## 3. Goals and non-goals

### 3.1 Goals

| ID | Goal |
|---|---|
| G1 | Record a finished block of time in ≤ 4 clicks and ≤ 5 seconds, without leaving the keyboard or the tray. |
| G2 | Start and stop a labelled stopwatch in one click each, with the running state visible at a glance. |
| G3 | Produce a single chronological log of every recorded session, with total time, client, type and record method per line. |
| G4 | Export that log to CSV and XLSX, filtered and optionally rounded to a billing increment, without ever altering the underlying record. |
| G5 | Work entirely offline, with no account, no telemetry, and a user-readable local data file. |
| G6 | Let the user's own vocabulary grow organically: any label typed once becomes a reusable chip. |

### 3.2 Non-goals for v1

| ID | Explicitly out of scope |
|---|---|
| NG1 | Multi-user, teams, roles, approval workflows. |
| NG2 | Cloud sync or a hosted backend of any kind. |
| NG3 | Invoicing, hourly rates, currency, tax. (Export feeds the user's existing invoicing tool.) |
| NG4 | Automatic activity tracking — screenshots, window-title capture, keystroke counting, productivity scores. This is a deliberate product-values decision, not a scheduling one. |
| NG5 | Mobile or web clients. |
| NG6 | Calendar or ticket-system integration (Outlook, Google Calendar, Jira). Candidate for v2. |
| NG7 | Two-way sync with Toggl / Clockify / Harvest. |
| NG8 | Sub-client structure (project → task → sub-task hierarchies). v1 has exactly two label dimensions: Client and Type. |

---

## 4. Users

**Primary persona — the billing professional.** Independent consultant, lawyer, accountant, architect or freelance engineer. Serves 3–15 active clients. Bills in tenths or quarters of an hour. Currently reconstructs the week on Friday afternoon from memory, calendar and sent-mail, and knows this under-counts. Technically comfortable but unwilling to administer a server.

**Secondary persona — the internal allocator.** Salaried employee who must allocate hours to cost centres, projects or matters for internal reporting. Does not bill, but must submit a defensible breakdown monthly. Cares about export shape more than about the timer.

### 4.1 Key scenarios

| # | Scenario | Mode |
|---|---|---|
| S1 | A 50-minute client call is about to start. User clicks the tray, clicks Start, picks the client. After the call, clicks Stop. | Start–Stop |
| S2 | User has just spent a few minutes answering three emails from two different clients. Opens the matrix, logs 6 min / Email / Nike, then 6 min / Email / Adidas. Elapsed effort: ~8 seconds. | Add Time |
| S3 | Friday 16:30. User reviews the week's log, spots a Tuesday afternoon with a 2-hour gap, adds a back-dated 90-minute Work entry for ASICS, then exports the week to XLSX rounded to 6-minute increments and attaches it to an invoice. | Both + export |
| S4 | User starts a timer, is pulled into a corridor conversation, and returns 40 minutes later. The app has noticed the idle period and asks what to do with it. | Start–Stop |
| S5 | A new client arrives. User types "Puma" into the client field once; it is a chip from then on. | Labels |

---

## 5. Competitive scan

### 5.0 Relationship to the existing "Chronicle" PRD

The project folder already contains a substantial body of work on this market, dated the same day: `time-tracking-PRD.docx` (a PRD for **Chronicle** — an AI-drafted, passive-capture, commercially-priced product for interrupt-driven IT consultants), `time-tracking-market-landscape.xlsx` (50 tools surveyed, with a shortlist comparison and published pricing) and `time-tracking-competitive-review.pptx`. **That research is the authoritative competitive source; the table below is a working summary, not a replacement for it.**

The two documents specify genuinely different products, and the difference should be made deliberately rather than by drift:

| | **Chronicle** (existing PRD) | **This PRD** |
|---|---|---|
| Capture model | Passive background capture + AI reconstruction of the day | Deliberate manual capture, two modes |
| Business model | Commercial SaaS, €19–29/user/month, practice tier | Personal tool; no pricing assumption |
| Data | Cloud/hybrid with a local-only mode | Local-only, no network, by definition |
| Core risk | AI attribution accuracy and correction cost | Whether the user opens the tray at all |
| Build size | A funded product with a validation study | A solo build reachable in weeks |

Three defensible ways to read this, and the choice is Q0 below:

1. **This is Chronicle's manual-capture layer, specified early.** Chronicle's own requirement 8.3 ("Capture — manual entry") needs a zero-ceremony manual path regardless of how good the AI gets, and the Add Time matrix is a stronger answer to it than anything in the market survey. Building this first produces a working capture surface and a real dataset, and defers every AI and cloud question.
2. **This is a separate, smaller product** — a local, free or one-off-priced tray tracker — that shares research with Chronicle but not a codebase.
3. **This supersedes Chronicle**, on the judgement that the AI-capture segment (Timely, Memtime, Timing, Rize) is crowded and that the correction-cost problem the Chronicle PRD itself identifies is the harder bet.

Reading (1) is the recommendation: it is the only option where the work is not wasted under any of the three. Under (1), the non-goals in §3.2 are *v1 non-goals for this component*, not permanent product positions, and the local-first principle P1 becomes "local-first in this layer" rather than a company-level promise.

| Tool | Model | Tray timer | Storage | Retroactive entry | Relevant gap |
|---|---|---|---|---|---|
| **Toggl Track** | Cloud, freemium | Yes — rich tray menu, idle detection with keep/discard/split, Pomodoro, global shortcuts, autotracker, offline cache | Cloud, local cache | Form-based | Account-bound; manual entry is a full form; feature surface far beyond a solo user's needs |
| **Clockify** | Cloud, freemium | Yes | Cloud | Form-based | Same; free tier is generous but data lives with the vendor |
| **ManicTime** | Local-first, commercial | Yes | Local DB | Yes, from the auto-captured timeline | Built around automatic activity capture — powerful but surveillance-shaped |
| **ActivityWatch** | Open source, local | Yes | Local | Poorly | Records what you did, not what you *intended*; no billing vocabulary |
| **Super Productivity** | Open source, local-first | Yes | Local, optional sync | Yes | Task-manager first, tracker second; individual-focused by design |
| **Kimai / Traggo / TimeTagger** | Self-hosted web | No | Server | Yes | Requires running and maintaining a server; no tray presence |
| **Timewarrior** | CLI, local | N/A | Local files | Yes | Powerful reporting, no GUI, terminal-only |

**What we take:** Toggl's idle-detection dialogue (keep / discard / discard-and-stop / log separately) is the correct interaction and is worth copying almost exactly. Its tray affordances — continue last entry, stop from hover — are proven. Local-first storage is the ActivityWatch/ManicTime strength.

**What we deliberately drop:** accounts, sync, teams, automatic capture, Pomodoro, project hierarchies, rates.

**Where we are differentiated:** no tool in the scan makes *retroactive micro-logging* a first-class mode. The Add Time matrix is the product's distinguishing feature; everything else is table stakes executed well.

---

## 6. Product principles

| ID | Principle | Consequence |
|---|---|---|
| P1 | **Local-first, no account.** | Data is a single SQLite file the user can copy, back up and read. No network calls, ever, in v1. |
| P2 | **The raw record is sacred.** | Durations are stored to the second, exactly as captured. Rounding, grouping and billing increments are applied at *export and display* time only, and are always reversible. |
| P3 | **Three clicks or it doesn't get used.** | Every primary action has a ≤ 3-click path from the tray icon. |
| P4 | **Keyboard-complete.** | Every action reachable by mouse is reachable by keyboard; the matrix is fully operable without the pointer. |
| P5 | **Never block.** | No modal blocks recording. Conflicts, overlaps and missing labels are flagged after the fact, never used to refuse an entry. |
| P6 | **No judgement.** | The app reports; it does not score, nag beyond an opt-in reminder, or compare the user to a target. |
| P7 | **Degrade, don't fail.** | If the tray is unavailable, if a label is missing, if the DB is locked — the app explains and offers a path, it does not lose the user's time data. |

---

## 7. Domain model

| Concept | Definition | Notes |
|---|---|---|
| **Entry** | One recorded block of time. The atomic unit of the log. | Has a start instant, an end instant, a duration, a client, a type, an optional note, and a record method. |
| **Client** | A label naming who the time is for. | User-extensible list. Case-preserving, case-insensitive for matching. Archivable, not deletable if referenced. |
| **Type** | A label naming the nature of the work. | Same mechanics as Client. Default seed: Email/Chat, Phone, Meeting/Call, Work. |
| **Note** | Free text attached to an entry. | Optional, ≤ 500 characters. Appears in exports. |
| **Record method** | How the entry came into existence: `Start-Stop` or `Add Time`. | Set by the system, never editable by the user. Present in the log and exports so the user can judge the reliability of a line. |
| **Session log** | The chronological list of all entries. | The "document" of the brief. Materialised as a view over the database, exported on demand. |
| **Running timer** | At most one, at any time. | Not an Entry until it is stopped. Persisted continuously so a crash cannot lose it. |

### 7.1 Entry attributes

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | opaque identifier | yes | Stable across edits and exports. |
| `started_at` | instant (UTC) + local timezone name | yes | Timezone stored so historical entries render correctly after travel or DST. |
| `ended_at` | instant (UTC) | yes | For Add Time entries this is the anchor point (§9.3.4). |
| `duration_seconds` | integer | yes | **Authoritative.** Not derived from the timestamps at read time — see FR-208 and §10. |
| `client_id` | reference | configurable | Mandatory by default; can be made optional in settings. |
| `type_id` | reference | configurable | Same. |
| `note` | text | no | |
| `record_method` | enum | yes | System-assigned. |
| `created_at`, `modified_at` | instants | yes | For audit and conflict resolution. |
| `is_edited` | boolean | yes | True if any field was changed after creation; surfaced in the log. |

---

## 8. Functional requirements

Priority: **M** = must have for v1.0, **S** = should have, **C** = could have / later phase.

### 8.1 Application shell and tray

| ID | Pri | Requirement |
|---|---|---|
| FR-101 | M | The application runs with no taskbar presence and no main window. Its sole persistent UI is a system tray / menu bar icon. |
| FR-102 | M | Left-click (primary activation) on the tray icon opens the **popover** — the main control surface (§9.2). Clicking elsewhere or pressing Esc dismisses it. |
| FR-103 | M | Right-click opens a native context menu containing at minimum: Start / Stop, Add Time…, Open log…, Settings…, Quit. |
| FR-104 | M | The tray icon visually distinguishes at least three states: **idle** (no timer), **running**, and **attention** (idle-time prompt pending, or unrecovered entry). |
| FR-105 | M | Hovering the tray icon shows a tooltip with the running timer's elapsed time, client and type, or "Not tracking". |
| FR-106 | S | Where the platform permits text in the tray/menu-bar area (macOS), the elapsed time of a running timer is displayed inline. Where it does not (Windows), the tooltip is the fallback. This asymmetry is accepted, not worked around. |
| FR-107 | M | Only one instance of the application may run. Launching a second instance surfaces the existing one's popover and exits. |
| FR-108 | M | The application can be configured to start automatically at user login. Default: off; offered once on first run. |
| FR-109 | S | A configurable global hotkey toggles the timer (start/stop) and a second opens the Add Time matrix, from any application. |
| FR-110 | M | If no system tray is available, the application must not silently fail: it shows an explanatory window offering a fallback windowed mode. |
| FR-111 | M | Quitting while a timer runs prompts: stop and save, keep running in background, or discard. |

### 8.2 Start–Stop mode

| ID | Pri | Requirement |
|---|---|---|
| FR-201 | M | The user can start a timer in one click from the popover or the context menu. |
| FR-202 | M | On start, Client and Type default to the most recently used pair. The user may change either while the timer runs or at stop. **Starting is never blocked on choosing a label** (principle P3/P5). |
| FR-203 | M | At most one timer runs at a time. Starting a new timer while one is running stops and saves the current one first, then starts the new one. A setting may require confirmation. |
| FR-204 | M | Stopping a timer creates an Entry with `record_method = Start-Stop` and returns the app to idle. |
| FR-205 | S | A stop confirmation sheet may be shown (setting, default on) allowing the user to adjust client, type and note before the entry is written. |
| FR-206 | M | The elapsed time updates at least once per second while the popover is open, and at least once per minute otherwise. |
| FR-207 | M | The running timer's state is persisted durably at least every 30 seconds. After a crash, power loss or forced reboot, the next launch offers to recover the entry up to the last persisted heartbeat, or to discard it. |
| FR-208 | M | Elapsed time is measured with a monotonic clock, not wall-clock arithmetic. A DST transition, a manual clock change or an NTP correction during a running timer must not alter the recorded duration. |
| FR-209 | M | **Idle detection.** After a configurable period of no keyboard or mouse input (default 10 minutes, 0 = off), the app raises a prompt offering four outcomes: keep the idle time, discard it, discard it and stop the timer, or log the idle period as a separate entry. |
| FR-210 | M | The idle prompt is non-blocking and non-destructive: if the user never answers, the timer keeps running and the idle time is kept. The prompt remains available from the tray (attention state) until answered or superseded. |
| FR-211 | M | Sleep, hibernation and lock are treated as idle: on wake, the app computes the away period and raises the same prompt. |
| FR-212 | S | Pause / resume. A paused timer accrues no duration; resuming continues the *same* entry. The entry records total paused time. |
| FR-213 | C | "Continue" — restart a timer with the client, type and note of any recent entry, in one click. |
| FR-214 | S | Entries shorter than a configurable minimum (default 60 seconds) prompt for confirmation before being saved, to catch accidental start/stop. |

### 8.3 Add Time mode (the matrix)

The interaction is specified in detail in §9.3. Requirements here define behaviour.

| ID | Pri | Requirement |
|---|---|---|
| FR-301 | M | The Add Time surface is a four-column matrix: **Time**, **Type**, **Client**, **Note**, presented as a grid of clickable chips (per the supplied mockup). |
| FR-302 | M | It composes exactly one pending entry at a time. It is a composer, not a grid of independent one-shot actions. |
| FR-303 | M | **Time column — additive.** Each duration chip (`+6min`, `+15min`, `+30min`, `+45min`) *adds* its value to a running pending total, which is displayed prominently. Clicking `+15min` twice yields 30 minutes. |
| FR-304 | M | The Time column includes a **Custom** affordance that accepts a free-form duration (`45`, `1:30`, `1h15`, `0.75h`) and adds it to the pending total. |
| FR-305 | M | The pending total can be cleared in one action and decremented (e.g. Shift-click on a chip subtracts its value). The total may never go below zero. |
| FR-306 | M | **Type column — single-select.** Exactly one type is selected at a time; clicking another replaces the selection. |
| FR-307 | M | **Client column — single-select.** Same semantics. |
| FR-308 | M | **Note column** — a single free-text field for the pending entry (not one per row). Optional. |
| FR-309 | M | Both Type and Client columns include a **Custom field** affordance that opens an inline text input. On commit the value is (a) applied to the pending entry and (b) added permanently to that column's label list (FR-401). |
| FR-310 | M | A **Add** action commits the pending entry. It is enabled only when the pending total > 0 and all mandatory labels are set. `Enter` is a keyboard equivalent. |
| FR-311 | M | On commit the app shows a brief non-modal confirmation naming what was logged (e.g. *"0:30 · Meeting/Call · ASICS — added"*), with an **Undo** affordance available for at least 10 seconds. |
| FR-312 | M | After commit the composer resets the pending total to zero but **retains** the selected Client and Type (sticky), because logging several blocks for one client in succession is the dominant pattern. |
| FR-313 | S | **Express mode** (setting, default off): when enabled, clicking a Time chip commits immediately using the currently selected Client and Type, turning the matrix into a one-click logger. |
| FR-314 | M | Entries created here have `record_method = Add Time`. |
| FR-315 | M | The matrix is fully keyboard-operable: digit keys select Time chips, letter accelerators select Type and Client chips, Tab reaches the note, Enter commits, Esc dismisses without committing. |
| FR-316 | S | The composer header carries a **date stepper** allowing the pending entry to be back-dated to a previous day (§9.3.4). |
| FR-317 | S | The matrix shows the day's running total for the selected date, so the user can see how much of the day is accounted for. |
| FR-318 | C | The chip sets are user-configurable: which durations appear, and the order and membership of the Type and Client columns (most-recently-used ordering by default). |

### 8.4 Labels

| ID | Pri | Requirement |
|---|---|---|
| FR-401 | M | Any Client or Type value typed into a Custom field is persisted to that dimension's label list and available as a chip thereafter. |
| FR-402 | M | Label matching on entry is case-insensitive and whitespace-normalised, so "nike", "Nike " and "Nike" resolve to one label. The first-entered casing is preserved for display. |
| FR-403 | M | On near-duplicate entry (edit distance ≤ 2 against an existing label), the app offers the existing label rather than silently creating a second one. The user may override. |
| FR-404 | M | Labels can be renamed. A rename propagates to every entry that references it. |
| FR-405 | M | Labels can be **archived** (hidden from chip lists, retained in historical entries). A label referenced by at least one entry cannot be hard-deleted. |
| FR-406 | S | Labels can be merged (fold label A into label B, re-pointing all entries). |
| FR-407 | S | Chip ordering per column: most-recently-used first by default; a label can be pinned to the front. |
| FR-408 | S | A colour may be assigned per Client, used in the log and chips. |
| FR-409 | M | The seed lists on first run are: Type — Email/Chat, Phone, Meeting/Call, Work. Client — empty, with a first-run prompt to add the first few. |

### 8.5 The session log

| ID | Pri | Requirement |
|---|---|---|
| FR-501 | M | A log window presents every entry, one per line, in chronological order. |
| FR-502 | M | Each line shows at minimum: date, start time, end time, **total time**, **client**, **type**, **record method**, note. Sort default: newest first, configurable. |
| FR-503 | M | The log can be filtered by date range (with presets: today, this week, last week, this month, last month, custom), by client, by type and by record method, and searched by note text. |
| FR-504 | M | Totals are shown for the current filter: grand total, and subtotals grouped by client and by type. |
| FR-505 | M | Entries are editable: duration, start/end, client, type, note. An edited entry is flagged `is_edited`. `record_method` is never editable. |
| FR-506 | M | Entries can be deleted, with undo available for the duration of the session and a confirmation for bulk deletion. |
| FR-507 | S | Entries can be split (one entry into two at a chosen point) and merged (adjacent entries with the same client and type combined). |
| FR-508 | S | Overlapping entries are flagged with a visible indicator and can be filtered for. Overlap is **never prevented** — the user may legitimately double-book. |
| FR-509 | S | A day view shows entries against a timeline with gaps visible, so unaccounted time is obvious at a glance. |
| FR-510 | C | A weekly grid view (clients × days) with per-cell totals. |

### 8.6 Export and rounding

| ID | Pri | Requirement |
|---|---|---|
| FR-601 | M | The current filtered view can be exported to **CSV** (UTF-8 with BOM for Excel compatibility, RFC 4180 quoting, configurable delimiter defaulting to the locale's). |
| FR-602 | M | The same can be exported to **XLSX**: a formatted table with a header row, frozen header, real duration values (not text), and a totals row. |
| FR-603 | M | Export columns are: Date, Start, End, Duration (decimal hours), Duration (h:mm), Client, Type, Record method, Note. Column selection is configurable. |
| FR-604 | M | **Rounding** may be applied at export: none, 6, 10, 15 or 30 minutes; always rounding up. The rounding setting is recorded in the export (a footer or a metadata sheet) so the recipient knows what was applied. |
| FR-605 | M | Rounding never mutates stored data (P2). Re-exporting with a different increment yields a different file from the same records. |
| FR-606 | M | **Rounding scope** is selectable: per entry, or per (day × client × type) group. This matters: three 2-minute emails rounded individually at 6 minutes bill 18 minutes; grouped, they bill 6. The default is per group, which is the more conservative and defensible choice. |
| FR-607 | S | An aggregated export mode produces one line per (day × client × type) rather than one line per entry, with notes concatenated. This is the shape most invoicing tools want. |
| FR-608 | S | Named export presets (column set + grouping + rounding + destination folder) can be saved and re-run in one click. |
| FR-609 | C | A print-ready PDF timesheet. |

### 8.7 Settings

| ID | Pri | Requirement |
|---|---|---|
| FR-701 | M | Settings cover: start at login; idle threshold; stop confirmation on/off; mandatory client/type; minimum entry duration; default rounding and scope for export; default export folder; global hotkeys; theme (system/light/dark); first day of week; time format. |
| FR-702 | S | Opt-in reminders: if no timer has run and no entry has been added for N minutes during configured working hours and days, show a passive notification. Off by default. |
| FR-703 | M | Settings are stored alongside the database and are included in backup/export of the data. |

### 8.8 Data management

| ID | Pri | Requirement |
|---|---|---|
| FR-801 | M | All data lives in a single local database file at a documented, user-visible path, plus a settings file. |
| FR-802 | M | The user can trigger a backup (a timestamped copy of the database) and can restore from one. |
| FR-803 | S | Automatic rolling backups (e.g. daily, last 14 kept) to a configurable folder. |
| FR-804 | M | Full data export (every entry and every label) to CSV/JSON for portability. |
| FR-805 | S | Import from CSV with column mapping, for migrating from a previous tool. |
| FR-806 | M | The database schema is versioned and migrations are applied automatically and idempotently on launch, with a pre-migration backup taken first. |

---

## 9. UI specification

### 9.1 Tray icon states

| State | Icon | Tooltip |
|---|---|---|
| Idle | Outline clock | "Not tracking" |
| Running | Filled clock / accent colour | "1:23 · Meeting/Call · ASICS" |
| Attention | Badge overlay | "Idle for 12 min — click to resolve" / "Unsaved session recovered" |

Icons must be legible at 16 px (Windows) and 22 px (X11), and must respect the platform's light/dark menu-bar treatment (a template image on macOS).

### 9.2 Popover

Opened by left-clicking the tray icon. Anchored to the icon. Dismissed on focus loss or Esc. Approximately 380 px wide; height varies by state.

**Idle state, top to bottom:**
1. Large elapsed display showing `0:00`, greyed.
2. Client selector and Type selector, pre-filled with the last used pair.
3. A primary **Start** button.
4. A secondary **Add Time** button, which switches the popover to the matrix (§9.3).
5. Today's total, and the three most recent entries as one-line "continue" rows.
6. A footer row: Open log · Settings.

**Running state:**
1. Live elapsed display, monospaced digits, updating each second.
2. Editable Client / Type / note for the running entry.
3. A primary **Stop** button; a secondary **Pause** (v1.1).
4. Started-at time and today's total.

### 9.3 Add Time matrix

The supplied mockup is normative for layout: a four-column table with a header row (Time · Category · Client · Note) and a column of chips beneath each heading, ending in a "Custom field" affordance.

#### 9.3.1 Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  Add time        ‹  Fri 11 Sep 2026  ›            Pending: 0:30  │
├───────────────┬───────────────┬───────────────┬──────────────────┤
│ Time          │ Category      │ Client        │ Note             │
├───────────────┼───────────────┼───────────────┼──────────────────┤
│ +6min         │ Email/Chat    │ Nike          │ ┌──────────────┐ │
│ +15min      ✓ │ Phone         │ Adidas        │ │              │ │
│ +30min        │ Meeting/Call ✓│ ASICS       ✓ │ │              │ │
│ +45min        │ Work          │ Reebok        │ └──────────────┘ │
│ Custom…       │ Custom…       │ Custom…       │                  │
├───────────────┴───────────────┴───────────────┴──────────────────┤
│  Today: 4:15                        [ Clear ]        [  Add  ]   │
└──────────────────────────────────────────────────────────────────┘
```

#### 9.3.2 Column semantics

- **Time** — additive accumulator. Click adds; Shift-click subtracts; the pending total in the header is the source of truth and is itself click-to-edit. A checkmark or count badge on a chip shows how many times it has contributed.
- **Category (Type)** — radio. One selected, highlighted with a filled background.
- **Client** — radio. Same treatment.
- **Note** — a single multi-line text field spanning the column, for the pending entry.
- **Custom…** — opens an inline input in place of the cell. Enter commits, Esc cancels. On commit for Type/Client, the value becomes a permanent chip.

#### 9.3.3 Commit

`Add` is disabled until pending total > 0 and mandatory labels are set; a tooltip on the disabled button says which condition is unmet. After commit: toast with Undo, pending total → 0:00, note cleared, Type and Client retained.

#### 9.3.4 Anchoring in time

An Add Time entry has a duration but no naturally observed start and end. The app assigns them:

- **Today:** the entry ends *now* (truncated to the minute) and starts `now − duration`.
- **A past date:** the entry starts immediately after the last existing entry on that date; if the date has no entries, it starts at the configured workday start (default 09:00).
- If this would place the start before the workday start or push the end past midnight, the entry is anchored to the workday start / clamped to 23:59 respectively, and flagged for review in the log.

Anchoring is a convenience, not a claim. Entries created this way are marked `Add Time` precisely so that anyone reading the log knows the timestamps are assigned rather than observed. The user can edit them in the log at any time.

#### 9.3.5 Keyboard map (matrix)

| Key | Action |
|---|---|
| `1`–`5` | Add the nth Time chip |
| `Shift`+`1`–`5` | Subtract the nth Time chip |
| `Q W E R T` | Select the nth Category chip |
| `A S D F G` | Select the nth Client chip |
| `Tab` | Focus the note |
| `Enter` | Commit |
| `Ctrl`/`Cmd`+`Z` | Undo last commit |
| `←` / `→` | Previous / next date |
| `Esc` | Dismiss without committing |

### 9.4 Log window

A conventional resizable window. Toolbar: date-range preset, client filter, type filter, method filter, search box, Export button. Table below with sortable columns per FR-502. Footer with totals per FR-504. Inline editing on double-click. Edited rows carry a subtle marker; overlapping rows carry a warning marker.

### 9.5 Accessibility

All interactive elements reachable by Tab with visible focus rings; chips expose accessible names and selected state to the platform accessibility API; colour is never the sole carrier of meaning (selected chips carry a checkmark as well as a fill); the UI is legible at 200 % display scaling and honours the system font size.

---

## 10. Edge cases and defined behaviour

| Situation | Required behaviour |
|---|---|
| Machine sleeps with a timer running | On wake, treat the sleep period as idle; raise the idle prompt (FR-211). The duration is not silently inflated. |
| Application crashes with a timer running | On next launch, offer recovery up to the last heartbeat (FR-207). |
| DST transition during a running timer | Duration is unaffected (monotonic clock, FR-208). Displayed start/end times remain correct in local terms via the stored timezone. |
| User changes system clock during a timer | Duration unaffected. A warning is logged. |
| Timer runs for more than 12 hours | At a configurable threshold (default 12 h), the app raises a "is this still running?" prompt. It does not auto-stop. |
| Add Time would create a negative or zero duration | `Add` stays disabled. Pending total is floored at zero. |
| Add Time overlaps a running timer | Permitted. Both entries are recorded and flagged as overlapping (FR-508). |
| Two labels differing only by case or trailing space | Resolved to one (FR-402). |
| Database file is locked or on an unavailable network drive | The app refuses to start silently; it shows a clear error with the path, and offers to choose a different location. A running timer is never lost — the heartbeat falls back to a local journal file. |
| Disk full on write | The entry is held in memory, the user is warned once, and writes retry. |
| Label referenced by entries is deleted | Not permitted; offer archive or merge instead (FR-405/406). |
| Tray unavailable (some Linux sessions) | Fallback windowed mode (FR-110). |
| Export target file is open in Excel | Detected; offer a new filename rather than failing silently. |
| Entry note exceeds 500 characters | Truncated with warning at input time, not at save time. |

---

## 11. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | Cold start to tray icon visible: ≤ 2 s on a mid-range 2022 laptop. |
| NFR-02 | Popover open latency: ≤ 150 ms. Matrix commit to toast: ≤ 100 ms. |
| NFR-03 | Idle memory footprint ≤ 150 MB RSS; idle CPU indistinguishable from zero (< 0.1 % average). |
| NFR-04 | The log window remains responsive (scroll, filter, sort under 200 ms) with 50 000 entries — roughly 20 years of heavy use. |
| NFR-05 | No network connections are made by the application in v1, under any circumstance. This is verifiable and should be verified in CI. |
| NFR-06 | No data leaves the device. No telemetry, no crash reporting upload, no update check without explicit opt-in. |
| NFR-07 | A power loss at any moment loses at most 30 seconds of a running timer and never corrupts the database. |
| NFR-08 | Windows 10/11, macOS 13+, and mainstream Linux desktops (GNOME, KDE, XFCE) are supported. Behaviour differences (e.g. FR-106) are documented rather than hidden. |
| NFR-09 | The application is usable by a first-time user, with no manual, to record a first entry within 60 seconds of launch. |
| NFR-10 | The database schema and file format are documented, so that the data is usable without the application. |

---

## 12. Privacy and compliance

The application processes client-identifying information (client names) and work descriptions. Because all processing is local and no data is transmitted, the vendor/developer is not a processor of the user's data and no data-processing agreement is required — a meaningful simplification for professionals under GDPR who would otherwise need one with a cloud time-tracking vendor.

Requirements: the data file location is documented and user-selectable (FR-801); full export is always available (FR-804); no analytics of any kind (NFR-06); the application must be capable of running on an air-gapped machine.

Note that this is a design property to preserve deliberately: the moment an optional sync feature is added, the compliance picture changes materially, and that trade-off should be made explicitly rather than incrementally.

---

## 13. Success metrics

| Metric | Target |
|---|---|
| Time to log a retroactive entry (measured, mouse, from tray click to toast) | < 5 seconds |
| Clicks to log a retroactive entry | ≤ 4 including opening the tray |
| Share of workdays in a month with at least one entry | > 90 % after four weeks of use |
| Share of entries created via Add Time | > 40 % — if this is low, the mode is not earning its place |
| Self-reported "hours captured that I would previously have lost" | > 3 h/week for the primary persona |
| Crash-loss incidents (time lost to a crash) | 0 |

---

## 14. Release plan

| Release | Contents | Exit criteria |
|---|---|---|
| **v0.1 — walking skeleton** | Tray icon, popover, start/stop, SQLite persistence, hard-coded labels, plain log window. | The author can track a full day and see the entries. |
| **v0.2 — the matrix** | Add Time matrix with additive time, single-select type/client, custom fields growing the label lists, undo. | Scenario S2 completes in under 5 seconds. |
| **v0.3 — trust** | Crash recovery, heartbeat, monotonic durations, idle detection with the four-way prompt, sleep/wake handling. | A forced power-off loses ≤ 30 s. |
| **v0.4 — the document** | Full log window: filter, search, edit, delete, totals. CSV + XLSX export with rounding and grouping. | Scenario S3 completes end to end. |
| **v0.5 — polish** | Settings, autostart, global hotkeys, theming, accessibility pass, label management (rename/archive/merge). | Usability test with one external user, no blockers. |
| **v1.0** | Packaging and installers for the three platforms, backup/restore, documentation, migration guide. | NFR targets met and measured. |
| **v1.1+** | Pause/resume, day timeline view, weekly grid, export presets, CSV import, reminders. | — |
| **v2 candidates** | Calendar read-only integration (propose entries from calendar events), Toggl/Clockify export format, a second label dimension (project under client), optional encrypted sync. | Re-evaluate NG2 and NG6 with usage data. |

---

## 15. Open questions

| # | Question | Bearing |
|---|---|---|
| Q0 | Is this the manual-capture layer of Chronicle, a separate smaller product, or a replacement for it? Every other open question is cheaper to answer after this one. Current assumption: reading (1) — Chronicle's manual-capture layer, built first. | §5.0 |
| Q1 | Should Client and Type be **mandatory** on an entry, or should an unlabelled entry be permitted and triaged later? A "log now, label later" inbox is lower friction but risks an unlabelled backlog. Current assumption: mandatory by default, with a setting. | FR-202, FR-310 |
| Q2 | Is one flat Client dimension sufficient, or is Client → Project needed before v1? Adding it later is a schema migration; adding it now doubles the width of the matrix. Current assumption: flat for v1. | NG8 |
| Q3 | Should the Add Time anchoring rule (§9.3.4) place entries after the last entry of the day, or should it simply record a date with no time-of-day at all and let the log sort by creation order? The latter is more honest but breaks the day-timeline view. | §9.3.4, FR-509 |
| Q4 | Default rounding scope — per entry or per day×client×type? Per group is more conservative; per entry is what many billing conventions assume. Current assumption: per group. | FR-606 |
| Q5 | Does the tooltip-only running display on Windows (FR-106) undermine goal G2 enough to justify an always-on-top mini-widget as an alternative? | FR-106 |
| Q6 | How aggressive should near-duplicate label detection be? Edit distance ≤ 2 catches "Adidas"/"Addidas" but will also flag genuinely distinct short labels. Current assumption: distance ≤ 2, with a one-click "no, keep both". | FR-403 |
| Q7 | Should the app ship with the four seed Types from the mockup, or ask the user to define their own on first run? Seeding speeds the first session; a blank slate produces a better-fitting vocabulary. Current assumption: seed, editable. | FR-409 |

---

## Appendix A — Seed labels

**Types (from the mockup):** Email/Chat · Phone · Meeting/Call · Work
**Suggested additions for the billing persona:** Travel · Admin · Research · Review · Drafting
**Clients:** none seeded; the first-run flow invites the user to add three.

## Appendix B — Rounding reference

Standard billing increments and what each costs in rounded-up time per entry:

| Increment | Also called | Max added per entry | Typical users |
|---|---|---|---|
| 6 min | tenth of an hour | 5 min 59 s | Law firms (the ABA describes law-firm billing records as commonly running in six-minute increments) |
| 10 min | sixth of an hour | 9 min 59 s | Some agencies |
| 15 min | quarter hour | 14 min 59 s | Accountants, bookkeepers, consultants |

Worked example — five entries of 6, 11, 17, 26 and 44 minutes (104 minutes exact):

| Rounding | Billed total | Uplift |
|---|---|---|
| None | 104 min | — |
| 6 min, per entry | 114 min | +9.6 % |
| 10 min, per entry | 130 min | +25 % |
| 15 min, per entry | 135 min | +30 % |

This is exactly why FR-605 requires that rounding never touch the stored record, and why FR-604 requires the applied increment to be stated in the export.

---

## Sources

- [Toggl Track desktop app for Windows — feature reference](https://support.toggl.com/en/articles/6176883-toggl-track-desktop-app-for-windows)
- [Clockify — Windows time tracking](https://clockify.me/windows-time-tracking)
- [MinuteDock — Billing increments explained: 6, 10 and 15 minutes](https://minutedock.com/academy/billing-increments-explained)
- [CosmoLex — Understanding attorney billing increments](https://www.cosmolex.com/blog/understanding-attorney-billing-increments-for-a-more-efficient-practice/)
- [Super Productivity — Best open-source time tracking apps 2026](https://super-productivity.com/blog/best-open-source-time-tracking-apps-2026/)
- [Qt 6 — QSystemTrayIcon class reference (platform notes)](https://doc.qt.io/qt-6/qsystemtrayicon.html)
