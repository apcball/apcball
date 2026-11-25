# Implementation prompt — `buz_production_planning`: Planning Dashboard

You are adding a dashboard to the Odoo 17 addon `buz_production_planning`
(repo root: `/Users/apichartball/work/apcball`, one addon per top-level directory).
Read `CLAUDE.md` at the repo root first.

## 0. What the user wants

The module computes plans (demand → make/buy suggestions → draft documents → finite-capacity
schedule → Gantt → Apply). Today there is no screen that answers "what needs my attention?" or
"where is the factory overloaded?". Build one page, **Planning → Dashboard**, for two readers:

- **The planner**, every morning: sees the work waiting in the selected plan and clicks straight
  into the list to act on it.
- **The factory manager**: sees load against capacity per work center, the bottlenecks, and how
  much of the schedule finishes on time. Reads, does not act.

Both use the same page: cards on top, charts below. The users are not technical; every label must
be understandable without the manual.

The dashboard shows **one plan at a time**: the latest plan of the current company by default,
with a selector to switch. Never add numbers across plans (plans overlap, sums would double count).

## 1. Guardrails

- Odoo 17 API only (`fields.Command`, `invisible=` expressions, `<tree>`; `from odoo import _`).
- The dashboard is **read-only**. It never writes, never changes a state, never creates a document.
  Every click only opens an existing view.
- No `sudo()`. Read through the ORM (`search_count`, `_read_group`, `search_read`) so the multi-company
  rules and access rights in `security/` apply. Scope to `self.env.companies`.
- Do not edit `static/src/gantt/*`, `engine/scheduler.py`, `engine/mrp_netting.py`.
  `engine/gantt.py` may be imported and reused; change it only if a helper must be extracted, and
  then keep `gantt_data` output identical (`tests/test_gantt.py` must stay green).
- Source strings in English, in JS through `_t`. Every new string gets a Thai translation in `i18n/th.po`.
- Do **not** commit or push. Do **not** touch production (`mog-prod`, `MOG_LIVE`).
- Do **not** change `version` in `__manifest__.py`; ask the user (proposed: `17.0.1.2.0`).
- Deploy to DEV only: `bash scripts/deploy.sh dev buz_production_planning`.
- Tests run on the real DEV database (side effects are permanent):
  `ssh dev "docker exec odoo odoo -d MOG_DEV -u buz_production_planning --test-enable --stop-after-init --no-http"`

Read these before writing anything:

| File | Why |
|---|---|
| `models/plan_run.py` | states, `_compute_counts`, `next_step` / `next_step_hint`, `gantt_data`, `action_open_*` |
| `engine/gantt.py` | `capacity_and_load`, `wc_group`: capacity and load per work center per day |
| `models/plan_suggestion.py`, `models/plan_schedule_line.py` | fields behind every number below |
| `views/plan_suggestion_views.xml`, `views/plan_schedule_line_views.xml`, `views/menus.xml` | action XML ids, search filters, menu tree |
| `static/src/gantt/gantt_action.js` | the module's own OWL client-action pattern (`orm.call`, `doAction`, registry) |
| `buz_stock_reservation/models/dashboard.py` + `static/src/js/dashboard.js` | smallest dashboard in this repo: AbstractModel + Chart.js via `loadJS` |
| `buz_asset_management/static/src/dashboard/chart_card.js` | a clean Chart.js wrapper component (redraw only when config changes, destroy on unmount). Copy the idea, do not depend on that addon |
| `tests/common.py`, `tests/test_gantt.py` | fixtures and how a JSON payload method is tested |
| `manual.md` | Thai user manual to update |

## 2. Server side

New `models/plan_dashboard.py`: `AbstractModel` `buz.plan.dashboard` (no table, no ACL row needed).

`@api.model get_dashboard_data(run_id=False, tz=None)` returns one JSON-safe dict
(`tz` = the browser timezone, as `gantt_data` receives it; fall back to the user's tz, then UTC):

- `runs`: plans the user can read in the active companies, newest first, state != `cancel`,
  capped at 30: `id`, `name`, `state`, `date_from`, `date_to`.
- `run`: the selected plan (`run_id` if given and readable, else the first of `runs`): `id`, `name`,
  `state` (+ label), `date_from`, `date_to`, planner name, `next_step`, `next_step_hint`.
  `false` when there is no plan; the page then shows an empty state with a "Create a plan" button.
- `cards`: list of `{key, label, value, tone, model, domain}`. `domain` is the exact domain used to
  count, so the list opened by a click always shows the same number of rows. `tone` is
  `danger` / `warning` / `info` / `muted` (muted when value is 0).
- `charts`: the datasets of section 4.
- `bottlenecks`: top 10 work centers by load ÷ capacity over the plan window.
- `updated_at`.

All domains start with `('run_id', '=', run.id)`.

### Cards

| key | Label | Model | Domain (after run) | tone |
|---|---|---|---|---|
| `to_review` | Suggestions to review | `buz.plan.suggestion` | `state = proposed` | info |
| `no_document` | Approved, no document yet | `buz.plan.suggestion` | `state = approved`, `document_state = none` | warning |
| `late_suggestions` | Late suggestions | `buz.plan.suggestion` | `is_late = True`, `state in (proposed, approved)` | danger |
| `buy_no_vendor` | Buy without vendor | `buz.plan.suggestion` | `action = buy`, `vendor_id = False`, `state in (proposed, approved)` | warning |
| `shortage_products` | Products short | `buz.plan.suggestion` | `shortage_qty > 0`, `state in (proposed, approved)`; value = distinct products | danger |
| `late_workorders` | Work orders finishing late | `buz.plan.schedule.line` | `is_late = True` | danger |
| `not_applied` | Schedule lines not applied | `buz.plan.schedule.line` | `state = proposed` | info |

Check each field and value against the model before using it; if a name differs, follow the code
and say so in the report.

### Load and capacity

Reuse `engine/gantt.py:capacity_and_load(worktime, workcenters, lines, window_start, window_end, tz)`
the same way `gantt_data` builds its arguments (`models/plan_run.py`, around line 315). Window: from
`run.date_from` to the later of `run.date_to` and the end of the last schedule line, capped at
26 weeks from `date_from` (an overloaded schedule runs past the horizon, and that tail is exactly
what the manager needs to see; say in the chart subtitle when the cap cut something off).
Work centers: those that have schedule lines in the plan. From the per-work-center, per-day result derive:

- per work center: total load minutes, total capacity minutes, load % (capacity 0 with load > 0 = overloaded);
- per ISO week (Monday start): total load hours and total capacity hours across work centers.

One call must stay fast on real volume (prod has about 1,226 open work orders; a full compute there
took 14 s, a schedule 3 s). Target: under 2 s for the whole payload. No per-record loops with queries
inside; group in SQL / `_read_group`. `capacity_and_load` loops lines × working intervals per work
center: measure it on the demo plan, and if it dominates, say so in the report rather than rewriting it.

## 3. Client side

New `static/src/dashboard/`: `plan_dashboard.js`, `plan_dashboard.xml`, `plan_dashboard.scss`
(+ a small chart wrapper component if useful). Register in `web.assets_backend` after the Gantt files.

- OWL component, services `orm` and `action`. Registry tag `buz_production_planning.dashboard`.
- Chart.js through `loadJS("/web/static/lib/Chart/Chart.js")` in `onWillStart`; charts created in
  `onMounted`, redrawn when data changes, destroyed in `onWillUnmount`.
- Header: title, plan selector (`runs`), plan state badge, date range, the plan's `next_step_hint`,
  buttons **Open plan**, **Gantt**, **Refresh**.
- Card row: one card per entry of `cards`; big number, label, colour by `tone`. Click →
  `doAction` of an `ir.actions.act_window` on `model` with the returned `domain`, list + form views,
  name = card label. Cards with value 0 stay visible, greyed, still clickable.
- Selecting another plan reloads the data; remember the last selected plan per browser
  (`localStorage`, wrapped in try/catch), falling back to the latest when it is gone.
- Loading state, empty state (no plan yet), and a plain message when a chart has no data
  (plan not scheduled yet → the load charts say "Schedule the plan to see load").
- Layout works at 1280 px and narrows to one column on a tablet. Follow Odoo backend styling
  (Bootstrap utilities, `o_` variables); no new fonts or icon sets.

## 4. Charts

| # | Title | Type | Data | Click |
|---|---|---|---|---|
| 1 | Load vs capacity by week | bars = load hours, line = capacity hours | weekly totals | schedule lines of that week |
| 2 | Busiest work centers | horizontal bars, load % of capacity, top 10, bars over 100 % in red, reference line at 100 % | `bottlenecks` | schedule lines of that work center |
| 3 | On-time schedule | doughnut, on time vs late, % on time in the centre | scheduled MOs of the plan; an MO is late when any of its schedule lines has `is_late` | schedule lines, late only |
| 4 | Suggestions by release week | stacked bars, Make / Buy, count of open suggestions per `date_release` week | suggestions `state in (proposed, approved)` | suggestions of that week |
| 5 | Document progress | horizontal stacked bar or doughnut by `document_state` (none / draft / open / done) | all non-rejected suggestions | suggestions with that `document_state` |

Colours: one fixed colour per meaning across the page (late/overload = red, on time = green,
Make and Buy two distinct neutral hues). Never colour alone: every chart has a legend or direct
labels, and tooltips show the real numbers with units (hours, %, lines).

## 5. Menu, action, security

- `views/plan_dashboard_views.xml`: `ir.actions.client` `action_buz_plan_dashboard`,
  tag `buz_production_planning.dashboard`. Add the file to `data` in the manifest before `views/menus.xml`.
- `views/menus.xml`: menu **Dashboard**, sequence 5, first child of `menu_buz_plan_root`, same groups
  as the root (planning users and MRP users). This makes the Planning app open on the dashboard.
- `get_dashboard_data` needs no group gate of its own: a user without read access to plans gets the
  normal access error. A read-only MRP user sees the dashboard and can open lists, nothing more.

## 6. Translations and manual

- `i18n/th.po`: all new strings, Python and JS. Note: `-u` does not overwrite existing th_TH terms in
  the DEV database; do not regenerate `th.po` from a DB export without diffing it.
- `manual.md`: add Dashboard to the menu table and a short section: what each card means, what each
  chart means, that numbers belong to the selected plan only.

## 7. Tests

New `tests/test_dashboard.py` (import it in `tests/__init__.py`), `@tagged('post_install', '-at_install')`,
built on `SchedulingCommon` / `BlanketCommon` from `tests/common.py`, modelled on `tests/test_gantt.py`:

- payload shape: all keys present, JSON serialisable;
- no plan at all → `run` is false, cards empty, no error;
- default plan = latest non-cancelled; explicit `run_id` is honoured; a cancelled or unreadable
  `run_id` falls back to the latest;
- each card: value equals `search_count(domain)` on its model, on a fixture with known counts
  (proposed, approved without document, late, buy without vendor, late line, unapplied line);
- numbers of a second plan never leak into the first;
- weekly load and capacity totals equal the sums of `capacity_and_load` for the same window;
- on-time: MO with one late line of three counts as one late MO;
- multi-company: a plan of another company is neither listed nor counted;
- a user with only `mrp.group_mrp_user` can call the method; a user with no MRP group gets an access error.

All existing tests must stay green (124 `test_` methods in `tests/` today; report the runner's own count before and after).

## 8. Verification on DEV

1. `bash scripts/deploy.sh dev buz_production_planning`, then the test command of section 1. Report pass/fail counts.
2. `pylint --load-plugins=pylint_odoo buz_production_planning/` — no new messages.
3. Odoo shell on DEV as a non-admin planner: call `get_dashboard_data()` on the demo plan
   `PLAN/2026/0037` (TEST-GANTT data), print the cards and time the call.
4. Browser check if a DEV login is available: page loads without console errors, plan selector
   works, each card opens a list whose row count equals the card. If there is no browser access,
   say so plainly in the report; do not claim the UI was checked.

## 9. Definition of done

- Planning → Dashboard exists, opens first, shows the latest plan, selector switches plans.
- 7 cards and 5 charts as specified; every number opens the matching list with the same count.
- Read-only, no sudo, multi-company safe, payload under 2 s on DEV demo data.
- New tests green, old tests green, pylint clean, `th.po` and `manual.md` updated.
- Nothing committed, version untouched, prod untouched.
- Final report: what was built, files touched, test and timing output, anything in this prompt
  that did not match the code and what you did instead, what was not verified.
