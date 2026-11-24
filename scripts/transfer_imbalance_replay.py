#!/usr/bin/env python3
"""DRY RUN ONLY. Per-origin cost for the transfers found by transfer_imbalance_dryrun.sh.

Replays the FIFO queue of every (product, source warehouse) from the start of history,
the same way stock_fifo_by_location._fifo_consume_rows does, but remembers which origin
layer each transfer-out layer consumed and at what cost. Then, per transfer:

  * out_value_replay vs the out layer actually booked  -> is the OUT side trustworthy?
    (MATCH: the booked FIFO cost is reproducible, so the IN side is what is wrong.
     MISMATCH: do not repair from the out value without a human look.)
  * origins really consumed vs the origin the position layer was linked to
    (origin_attribution WRONG = landed cost on that receipt was mis-attributed).

Read-only: it only runs SELECTs (PGOPTIONS default_transaction_read_only=on) and writes
CSV files into <outdir>. Run transfer_imbalance_dryrun.sh into the same <outdir> first.

Usage: scripts/transfer_imbalance_replay.py <outdir> [ssh-host] [scope]
  scope  'warehouse' (default): one queue per (product, source warehouse)
         'product': one queue per product over ALL warehouses. Transfers built by
         stock_by_locations call _get_fifo_candidates without fifo_warehouse_id, which
         falls back to every warehouse, so this can reproduce the booked value better.

Writes into <outdir>:
  replay_by_transfer.csv   one row per transfer: replay status, per-origin consumption
  detail_with_replay.csv   detail.csv + replay_status / out_value_replay / origin columns
  replay_summary.csv       counts and THB by replay status
"""
import collections
import csv
import io
import json
import shlex
import subprocess
import sys

EPS = 1e-4


def psql_csv(host, sql, variables=None):
    """Run one SELECT on the remote DB, read-only, and return csv.DictReader rows.

    ``variables`` are handed to psql with -v and used in the SQL as :'name' (psql quotes
    them as literals), so values never get pasted into the query text.
    """
    var_args = "".join(f" -v {shlex.quote(f'{k}={v}')}" for k, v in (variables or {}).items())
    script = (
        "set -euo pipefail\n"
        "PGPASS=$(grep -E '^db_password' /etc/instance1.conf | cut -d= -f2 | tr -d ' ')\n"
        'export PGPASSWORD="$PGPASS"\n'
        "export PGOPTIONS='-c default_transaction_read_only=on'\n"
        "psql -X -h localhost -U odoo MOG_LIVE --csv -v ON_ERROR_STOP=1" + var_args + " <<'SQLEOF'\n"
        + sql + "\nSQLEOF\n"
    )
    out = subprocess.run(["ssh", host, "bash", "-s"], input=script, text=True,
                         capture_output=True, check=True).stdout
    return list(csv.DictReader(io.StringIO(out)))


def replay_queue(rows):
    """rows: dicts ordered by (create_date, id). Returns (consumption, shortage, inverted).

    consumption: {out_layer_id: [(candidate_id, origin_id, qty, value, candidate_warehouse_id), ...]}
    Mirrors _fifo_consume_rows: candidates consumed in insertion order at their live
    rate value/qty; quantity == 0 rows are revaluations that top up the layer they point
    at (stock_valuation_layer_id).
    """
    pool = collections.OrderedDict()  # id -> {'qty', 'value', 'origin'}
    consumption = {}
    shortage = {}
    inverted = 0
    previous_id = 0
    for r in rows:
        lid = int(r["id"])
        if lid < previous_id:
            inverted += 1
        previous_id = max(previous_id, lid)
        qty = float(r["quantity"] or 0)
        value = float(r["value"] or 0)
        if qty > 0:
            if lid not in pool:
                origin = int(r["origin_valuation_layer_id"]) if r["origin_valuation_layer_id"] else lid
                pool[lid] = {"qty": qty, "value": value, "origin": origin,
                             "wh": int(r["warehouse_id"] or 0)}
        elif qty < 0:
            to_consume = -qty
            taken_rows = []
            for pid in list(pool):
                if to_consume <= EPS:
                    break
                entry = pool[pid]
                available = entry["qty"]
                if available <= 0:
                    del pool[pid]
                    continue
                taken = min(available, to_consume)
                unit_cost = entry["value"] / available
                entry["qty"] -= taken
                entry["value"] -= taken * unit_cost
                to_consume -= taken
                taken_rows.append((pid, entry["origin"], taken, taken * unit_cost, entry["wh"]))
                if entry["qty"] <= EPS:
                    del pool[pid]
            consumption[lid] = taken_rows
            if to_consume > EPS:
                shortage[lid] = to_consume
        else:
            target = r["stock_valuation_layer_id"]
            if target and int(target) in pool:
                pool[int(target)]["value"] += value
    return consumption, shortage, inverted


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
    host = sys.argv[2] if len(sys.argv) > 2 else "mog-prod"
    scope = sys.argv[3] if len(sys.argv) > 3 else "warehouse"
    if scope not in ("warehouse", "product"):
        sys.exit("scope must be 'warehouse' or 'product'")
    qkey = (lambda p, w: (p, 0)) if scope == "product" else (lambda p, w: (p, w))

    with open(f"{outdir}/detail.csv", newline="") as fh:
        detail = list(csv.DictReader(fh))
    if not detail or "source_wh_id" not in detail[0]:
        sys.exit("detail.csv missing or without source_wh_id: rerun transfer_imbalance_dryrun.sh first")
    move_ids = sorted({int(r["stock_move_id"]) for r in detail})
    print(f">>> {len(move_ids)} transfers, {len(detail)} layers to analyse")

    # 1. every layer of those transfers (out layers + current position layers)
    id_list = ",".join(str(i) for i in move_ids)
    move_layers = psql_csv(host, f"""
        SELECT id, stock_move_id, product_id, warehouse_id, quantity, value,
               origin_valuation_layer_id, is_position_layer
        FROM stock_valuation_layer
        WHERE stock_move_id IN ({id_list}) AND stock_landed_cost_id IS NULL AND quantity <> 0""")
    by_move = collections.defaultdict(list)
    for r in move_layers:
        by_move[int(r["stock_move_id"])].append(r)

    # 2. full queue history of each (product, source warehouse)
    pairs = sorted({qkey(int(r["product_id"]), int(r["warehouse_id"]))
                    for lst in by_move.values() for r in lst if float(r["quantity"]) < 0})
    print(f">>> replaying {len(pairs)} queues (scope={scope})")
    if scope == "product":
        join = f"""JOIN (VALUES {",".join(f"({p})" for p, _ in pairs)}) AS k(product_id)
          ON k.product_id = l.product_id"""
    else:
        join = f"""JOIN (VALUES {",".join(f"({p},{w})" for p, w in pairs)}) AS k(product_id, warehouse_id)
          ON k.product_id = l.product_id AND k.warehouse_id = l.warehouse_id"""
    history = psql_csv(host, f"""
        SELECT l.id, l.product_id, l.warehouse_id, l.quantity, l.value,
               l.stock_valuation_layer_id, l.origin_valuation_layer_id
        FROM stock_valuation_layer l
        {join}
        WHERE l.company_id = 1
        ORDER BY l.create_date, l.id""")
    queues = collections.defaultdict(list)
    for r in history:
        queues[qkey(int(r["product_id"]), int(r["warehouse_id"] or 0))].append(r)
    print(f">>> {len(history)} history rows fetched")

    consumption = {}
    shortage = {}
    inverted_by_queue = {}
    for key, rows in queues.items():
        cons, short, inv = replay_queue(rows)
        consumption.update(cons)
        shortage.update(short)
        inverted_by_queue[key] = inv

    # 3. per transfer
    result = {}
    for mid in move_ids:
        layers = by_move[mid]
        outs = [r for r in layers if float(r["quantity"]) < 0]
        poss = [r for r in layers if float(r["quantity"]) > 0]
        product = int(outs[0]["product_id"]) if outs else None
        key = qkey(product, int(outs[0]["warehouse_id"])) if outs else None
        out_actual = -sum(float(r["value"]) for r in outs)
        taken = [t for r in outs for t in consumption.get(int(r["id"]), [])]
        out_replay = sum(t[3] for t in taken)
        out_wh = int(outs[0]["warehouse_id"]) if outs else 0
        qty_other_wh = sum(t[2] for t in taken if t[4] != out_wh)
        short = sum(shortage.get(int(r["id"]), 0.0) for r in outs)
        per_origin = collections.OrderedDict()
        for _, origin, qty, value, _wh in taken:
            q, v = per_origin.get(origin, (0.0, 0.0))
            per_origin[origin] = (q + qty, v + value)
        pos_origins = sorted({int(r["origin_valuation_layer_id"]) for r in poss if r["origin_valuation_layer_id"]})
        replay_origins = sorted(per_origin)
        if not outs or not taken:
            status = "NO_QUEUE"
        elif short > EPS:
            status = "SHORTAGE"
        elif abs(out_actual - out_replay) <= max(1.0, 0.005 * abs(out_actual)):
            status = "MATCH"
        else:
            status = "MISMATCH"
        if status in ("MATCH", "MISMATCH") and inverted_by_queue.get(key):
            status += "_INVERTED_QUEUE"
        result[mid] = {
            "stock_move_id": mid, "product_id": product,
            "out_value_actual": round(out_actual, 2), "out_value_replay": round(out_replay, 2),
            "replay_status": status,
            "shortage_qty": round(short, 4),
            "qty_taken_from_other_warehouses": round(qty_other_wh, 4),
            "origins_replay": json.dumps([[o, round(q, 4), round(v, 2)] for o, (q, v) in per_origin.items()]),
            "origins_linked_on_position_layers": json.dumps(pos_origins),
            "origin_attribution": "OK" if pos_origins == replay_origins else (
                "WRONG" if replay_origins else "UNKNOWN"),
        }

    # 4. write
    cols = ["stock_move_id", "product_id", "out_value_actual", "out_value_replay", "replay_status",
            "shortage_qty", "qty_taken_from_other_warehouses", "origins_replay", "origins_linked_on_position_layers", "origin_attribution"]
    with open(f"{outdir}/replay_by_transfer.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for mid in move_ids:
            w.writerow(result[mid])
    extra = ["replay_status", "out_value_replay", "origin_attribution", "origins_replay"]
    with open(f"{outdir}/detail_with_replay.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detail[0].keys()) + extra)
        w.writeheader()
        for r in detail:
            res = result[int(r["stock_move_id"])]
            w.writerow({**r, **{k: res[k] for k in extra}})

    agg = collections.OrderedDict()
    for r in detail:
        res = result[int(r["stock_move_id"])]
        a = agg.setdefault(res["replay_status"], [set(), 0, 0.0, 0.0, 0.0])
        a[0].add(int(r["stock_move_id"]))
        a[1] += 1
        a[2] += float(r["delta"])
        a[3] += float(r["delta_on_hand"])
        a[4] += float(r["delta_left"])
    wrong = sum(1 for r in result.values() if r["origin_attribution"] == "WRONG")
    verified = [r for r in result.values() if r["replay_status"].startswith("MATCH")]
    other_wh = sum(1 for r in verified if r["qty_taken_from_other_warehouses"] > EPS)
    with open(f"{outdir}/replay_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["replay_status", "transfers", "layers", "delta_thb", "delta_on_hand_thb", "delta_left_thb"])
        for status, (moves, layers, d, on, left) in sorted(agg.items()):
            w.writerow([status, len(moves), layers, round(d, 2), round(on, 2), round(left, 2)])
        w.writerow(["TRANSFERS_WITH_WRONG_ORIGIN_ATTRIBUTION", wrong, "", "", "", ""])
        w.writerow(["VERIFIED_TRANSFERS_THAT_CONSUMED_OTHER_WAREHOUSE_LAYERS", other_wh, f"of {len(verified)}", "", "", ""])
    print(">>> replay_summary.csv:")
    print(open(f"{outdir}/replay_summary.csv").read())


if __name__ == "__main__":
    main()
