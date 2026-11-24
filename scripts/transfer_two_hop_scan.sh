#!/usr/bin/env bash
# READ-ONLY scan on mog-prod (session forced default_transaction_read_only).
# Finds the 301010008/FG10 pattern: a two-hop transfer A -> B -> C where
#   hop 1 in-layer I (at B) carries ONE origin layer X (origin_valuation_layer_id,
#   no consumed_origin_splits) but its unit cost differs from X (the units really
#   came from several A layers at a blended cost), and
#   hop 2 out-layer O (at B, later, qty <= I.qty) is priced at X's unit cost
#   instead of I's.  gap = |O.qty| * (O.unit_cost - I.unit_cost)  (+ = out booked
#   higher than in; the difference lands as residual value at B and C).
# One output row per O (earliest matching I). Heuristic: it matches by unit
# cost, not by explicit consumption links, so treat counts as candidates.
#
# Usage: scripts/transfer_two_hop_scan.sh [out.csv]
set -euo pipefail
OUT="${1:-transfer_two_hop_scan.csv}"

SQL=$(cat <<'SQLEOF'
\copy (WITH ins AS (SELECT l.id i_id, l.product_id, l.warehouse_id wh, l.create_date i_date, l.quantity i_qty, l.unit_cost i_uc, o.id x_id, o.unit_cost x_uc FROM stock_valuation_layer l JOIN stock_valuation_layer o ON o.id=l.origin_valuation_layer_id WHERE l.quantity>0 AND l.description ILIKE 'transfer in%' AND l.consumed_origin_splits IS NULL AND abs(l.unit_cost-o.unit_cost)>0.005), outs AS (SELECT id o_id, product_id, warehouse_id wh, create_date o_date, quantity o_qty, unit_cost o_uc, stock_move_id o_move FROM stock_valuation_layer WHERE quantity<0 AND description ILIKE 'transfer out%'), pairs AS (SELECT DISTINCT ON (o.o_id) ins.i_id, ins.x_id, o.o_id, ins.product_id, ins.wh, ins.i_date, o.o_date, o.o_move, ins.i_qty, -o.o_qty AS o_qty, ins.i_uc, ins.x_uc, o.o_uc FROM ins JOIN outs o ON o.product_id=ins.product_id AND o.wh=ins.wh AND o.o_date>ins.i_date AND -o.o_qty<=ins.i_qty AND abs(o.o_uc-ins.x_uc)<0.0005 AND abs(o.o_uc-ins.i_uc)>0.005 ORDER BY o.o_id, ins.i_date) SELECT p.default_code AS product_code, w.code AS via_warehouse, pr.i_id AS in_layer, pr.x_id AS origin_layer, pr.o_id AS out_layer, pr.o_move AS out_move, pr.i_date::date AS in_date, pr.o_date::date AS out_date, pr.o_qty AS out_qty, round(pr.i_uc,4) AS in_unit_cost, round(pr.x_uc,4) AS origin_unit_cost, round(pr.o_uc,4) AS out_unit_cost, round(pr.o_qty*(pr.o_uc-pr.i_uc),2) AS gap, CASE WHEN pr.i_date < '2026-03-30 17:00' THEN 'pre-cutoff' WHEN pr.i_date < '2026-09-16' THEN 'cutoff..2026-09-15' ELSE '2026-09-16+' END AS in_period FROM pairs pr JOIN product_product p ON p.id=pr.product_id JOIN stock_warehouse w ON w.id=pr.wh ORDER BY abs(pr.o_qty*(pr.o_uc-pr.i_uc)) DESC) TO STDOUT WITH CSV HEADER
SQLEOF
)

PW_CMD='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"; PGOPTIONS="-c default_transaction_read_only=on" psql -h localhost -U odoo MOG_LIVE -q -v ON_ERROR_STOP=1'
printf '%s\n' "$SQL" | ssh mog-prod "$PW_CMD" > "$OUT"
printf '\xef\xbb\xbf' | cat - "$OUT" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
python3 -I - "$OUT" <<'PY'
import csv, sys, collections
r = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))
print("candidate two-hop pairs:", len(r), "| products:", len({x["product_code"] for x in r}))
tot = collections.defaultdict(lambda: [0, 0.0, 0.0])
for x in r:
    g = float(x["gap"]); a = tot[x["in_period"]]
    a[0] += 1; a[1] += g; a[2] += abs(g)
for k, (n, net, ab) in sorted(tot.items()):
    print(f"  {k:<20} n={n:<5} net gap={net:>12,.2f}  abs gap={ab:>12,.2f}")
big = [x for x in r if abs(float(x["gap"])) >= 100]
print("pairs with |gap| >= 100:", len(big))
known = [x for x in r if x["out_layer"] == "209437"]
print("known case 301010008 (out layer 209437) found:", bool(known), known[0]["gap"] if known else "")
PY
