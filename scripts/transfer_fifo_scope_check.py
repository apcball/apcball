#!/usr/bin/env python3
"""DRY RUN ONLY. How often does an inter-warehouse transfer cost itself from other
warehouses' FIFO layers, and since when?

stock_by_locations prices the transfer-out layer through _run_fifo ->
_get_fifo_candidates WITHOUT the 'fifo_warehouse_id' context key, and the override then
falls back to every warehouse. Reproduced deterministically on DEV by
stock_fifo_by_location/tests/test_transfer_fifo_scope.py. This measures it on real data.

For every transfer whose position layer was created in the window, the transfer-out
layer is compared with two replays of the FIFO history (same engine as
_fifo_consume_rows, see transfer_imbalance_replay.replay_queue):
  * scoped : one queue per (product, source warehouse)  -- what the design intends
  * global : one queue per product over all warehouses  -- what the code path does

Status per transfer (booked out value vs replay, tolerance max(1 THB, 0.5%)):
  BOTH      both replays reproduce the booked value (no evidence either way; typically the
            queue had a single candidate / same cost)
  GLOBAL    only the global replay does -> the transfer was costed across warehouses
  SCOPED    only the scoped replay does
  NEITHER   neither does (backdating, reordered ids, replay cannot know)

Read-only (PGOPTIONS default_transaction_read_only=on). Writes <outdir>/scope_by_month.csv.

Usage: scripts/transfer_fifo_scope_check.py <since> <until> <outdir> [ssh-host]
"""
import collections
import csv
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("replay", os.path.join(HERE, "transfer_imbalance_replay.py"))
replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay)

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$")

# transfers = moves that got a position layer in the window (:'since' / :'until' are psql variables)
WINDOW = ("SELECT DISTINCT stock_move_id FROM stock_valuation_layer WHERE is_position_layer "
          "AND create_date >= :'since' AND create_date < :'until'")
OUT_LAYERS_SQL = """
SELECT l.id, l.stock_move_id, l.product_id, l.warehouse_id, l.value,
       to_char(l.create_date, 'YYYY-MM') AS month, to_char(l.create_date, 'YYYY-MM-DD') AS day,
       sm.reference
FROM stock_valuation_layer l
JOIN stock_move sm ON sm.id = l.stock_move_id
WHERE l.stock_landed_cost_id IS NULL AND l.quantity < 0 AND l.company_id = 1
  AND l.stock_move_id IN (@WINDOW@)"""
HISTORY_SQL = """
SELECT id, product_id, warehouse_id, quantity, value, stock_valuation_layer_id,
       origin_valuation_layer_id
FROM stock_valuation_layer
WHERE company_id = 1 AND product_id IN (
  SELECT DISTINCT l.product_id FROM stock_valuation_layer l
  WHERE l.stock_landed_cost_id IS NULL AND l.quantity < 0 AND l.company_id = 1
    AND l.stock_move_id IN (@WINDOW@))
ORDER BY create_date, id"""


def close(actual, replayed):
    return abs(actual - replayed) <= max(1.0, 0.005 * abs(actual))


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    since, until, outdir = sys.argv[1:4]
    host = sys.argv[4] if len(sys.argv) > 4 else "mog-prod"
    if not (TS_RE.match(since) and TS_RE.match(until)):
        sys.exit("since/until must look like 'YYYY-MM-DD[ HH:MM:SS]'")
    os.makedirs(outdir, exist_ok=True)
    variables = {"since": since, "until": until}

    outs = replay.psql_csv(host, OUT_LAYERS_SQL.replace("@WINDOW@", WINDOW), variables)
    print(">>> %d transfer-out layers in window" % len(outs))
    history = replay.psql_csv(host, HISTORY_SQL.replace("@WINDOW@", WINDOW), variables)
    by_product = collections.defaultdict(list)
    for r in history:
        by_product[int(r["product_id"])].append(r)
    print(">>> %d products, %d history rows" % (len(by_product), len(history)))

    # replays: global per product, scoped per (product, warehouse)
    glob = {}
    scoped = {}
    for pid, rows in by_product.items():
        glob[pid] = replay.replay_queue(rows)[:2]
        per_wh = collections.defaultdict(list)
        wh_of = {int(r["id"]): int(r["warehouse_id"] or 0) for r in rows}
        for r in rows:
            wh = int(r["warehouse_id"] or 0)
            # qty-0 revaluation / price-difference layers often carry no warehouse; they
            # adjust the layer they point at, so they belong to that layer's queue.
            if not wh and float(r["quantity"] or 0) == 0 and r["stock_valuation_layer_id"]:
                wh = wh_of.get(int(r["stock_valuation_layer_id"]), 0)
            per_wh[wh].append(r)
        for wh, wrows in per_wh.items():
            scoped[(pid, wh)] = replay.replay_queue(wrows)[:2]

    # one transfer = one stock_move (sum its out layers)
    moves = {}
    for r in outs:
        lid, mid, pid = int(r["id"]), int(r["stock_move_id"]), int(r["product_id"])
        wh = int(r["warehouse_id"] or 0)
        m = moves.setdefault(mid, {"actual": 0.0, "glob": 0.0, "scoped": 0.0, "other_qty": 0.0,
                                   "short_g": 0.0, "short_s": 0.0, "month": r["month"],
                                   "day": r["day"], "reference": r["reference"], "product": pid})
        m["actual"] += -float(r["value"])
        gcons, gshort = glob[pid]
        taken = gcons.get(lid, [])
        m["glob"] += sum(t[3] for t in taken)
        m["other_qty"] += sum(t[2] for t in taken if t[4] != wh)
        m["short_g"] += gshort.get(lid, 0.0)
        scons, sshort = scoped.get((pid, wh), ({}, {}))
        m["scoped"] += sum(t[3] for t in scons.get(lid, []))
        m["short_s"] += sshort.get(lid, 0.0)

    table = collections.OrderedDict()
    detail_rows = []
    for mid, m in sorted(moves.items(), key=lambda kv: (kv[1]["month"], kv[0])):
        g_ok = m["short_g"] <= replay.EPS and close(m["actual"], m["glob"])
        s_ok = m["short_s"] <= replay.EPS and close(m["actual"], m["scoped"])
        status = "BOTH" if g_ok and s_ok else "GLOBAL" if g_ok else "SCOPED" if s_ok else "NEITHER"
        detail_rows.append([mid, m["reference"], m["day"], m["product"], status, round(m["actual"], 2),
                            round(m["glob"], 2), round(m["scoped"], 2), round(m["other_qty"], 4)])
        row = table.setdefault(m["month"], collections.Counter())
        row["transfers"] += 1
        row[status] += 1
        if status == "GLOBAL":
            row["other_qty"] += m["other_qty"]
            row["booked_minus_scoped"] += m["actual"] - m["scoped"]

    with open(os.path.join(outdir, "scope_by_transfer.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["stock_move_id", "reference", "day", "product_id", "status", "out_booked",
                    "out_replay_global", "out_replay_scoped", "qty_from_other_wh"])
        w.writerows(detail_rows)
    path = os.path.join(outdir, "scope_by_month.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["month", "transfers", "BOTH", "GLOBAL", "SCOPED", "NEITHER",
                    "global_pct_of_decidable", "qty_from_other_wh", "booked_minus_scoped_thb"])
        for month, c in table.items():
            decidable = c["GLOBAL"] + c["SCOPED"]
            w.writerow([month, c["transfers"], c["BOTH"], c["GLOBAL"], c["SCOPED"], c["NEITHER"],
                        "%.0f%%" % (100 * c["GLOBAL"] / decidable) if decidable else "",
                        round(c["other_qty"], 2), round(c["booked_minus_scoped"], 2)])
    with open(path) as fh:
        print(fh.read())


if __name__ == "__main__":
    main()
