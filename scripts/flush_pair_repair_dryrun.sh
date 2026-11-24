#!/usr/bin/env bash
# DRY-RUN ONLY. Proposes paired SVL layers to repair "class A" FIFO Reset Flush
# pairs (per-warehouse SVL != quant, but gap == -flush qty on every warehouse of
# the product and total ledger == total quant). Writes NOTHING: the session is
# forced read-only (default_transaction_read_only) and the script only emits a CSV.
#
# Usage: scripts/flush_pair_repair_dryrun.sh [out.csv]   (runs against mog-prod)
#
# Two value policies are emitted side by side for accounting to choose from:
#   opt1_*  undo the flush exactly: qty = -flush_qty, value = -flush_value
#           (changes total inventory value by -sum(flush_value) per product)
#   opt2_*  move qty only, value-neutral per product: qty_delta x one reference
#           unit cost per product (avg |flush value| / |flush qty| over its flush
#           layers), so the two sides cancel (total value unchanged)
#   opt3_*  move qty only, value-neutral per product, priced at the average unit
#           cost of the warehouse that physically holds the units (the one whose
#           SVL is short, i.e. qty_delta > 0). Falls back to the other
#           warehouse's avg cost when that is empty; NO_COST_BASIS = manual.
# Fix BOTH sides or neither: every proposed row pair sums to qty 0 per product.
set -euo pipefail
OUT="${1:-flush_pair_repair_dryrun.csv}"

SQL=$(cat <<'SQLEOF'
\copy (WITH pw AS (SELECT coalesce(s.product_id,q.product_id) product_id, coalesce(s.warehouse_id,q.warehouse_id) wh, coalesce(s.sq,0) svl_qty, coalesce(s.sv,0) svl_val, coalesce(q.qty,0) quant, coalesce(f.fq,0) flush_qty, coalesce(f.fv,0) flush_val FROM (SELECT product_id,warehouse_id,sum(quantity) sq,sum(value) sv FROM stock_valuation_layer WHERE warehouse_id IS NOT NULL GROUP BY 1,2) s FULL JOIN (SELECT q.product_id, sl.warehouse_id, sum(q.quantity) qty FROM stock_quant q JOIN stock_location sl ON sl.id=q.location_id WHERE sl.usage='internal' AND sl.warehouse_id IS NOT NULL GROUP BY 1,2) q ON q.product_id=s.product_id AND q.warehouse_id=s.warehouse_id LEFT JOIN (SELECT product_id,warehouse_id,sum(quantity) fq,sum(value) fv FROM stock_valuation_layer WHERE stock_move_id IS NULL AND description LIKE 'FIFO Reset Flush%' GROUP BY 1,2) f ON f.product_id=coalesce(s.product_id,q.product_id) AND f.warehouse_id=coalesce(s.warehouse_id,q.warehouse_id)), cls_a AS (SELECT product_id FROM pw GROUP BY product_id HAVING count(*) FILTER (WHERE abs(svl_qty-quant)>.0001) > 0 AND abs(sum(svl_qty-quant)) <= .0001 AND abs(sum(flush_qty)) <= .0001 AND bool_and(abs(svl_qty-quant)<=.0001 OR abs((quant-svl_qty)+flush_qty)<=.0001)) SELECT p.default_code AS product_code, w.code AS warehouse, round(pw.svl_qty,2) AS svl_qty_now, round(pw.quant,2) AS quant, round(pw.svl_val,2) AS svl_val_now, round(pw.quant-pw.svl_qty,2) AS qty_delta, round(-pw.flush_val,2) AS opt1_value_delta, round((pw.quant-pw.svl_qty) * (SELECT sum(abs(o.flush_val))/NULLIF(sum(abs(o.flush_qty)),0) FROM pw o WHERE o.product_id=pw.product_id),2) AS opt2_value_delta, round((pw.quant-pw.svl_qty)*(CASE WHEN coalesce((SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty>0),0)>0 THEN (SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty>0) WHEN coalesce((SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty<0),0)>0 THEN (SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty<0) END),2) AS opt3_value_delta, CASE WHEN coalesce((SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty>0),0)>0 THEN 'recv_wh_avg' WHEN coalesce((SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty<0),0)>0 THEN 'src_wh_avg_fallback' ELSE 'NO_COST_BASIS' END AS opt3_basis, round((CASE WHEN coalesce((SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty>0),0)>0 THEN (SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty>0) WHEN coalesce((SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty<0),0)>0 THEN (SELECT sum(o.svl_val)/NULLIF(sum(o.svl_qty),0) FROM pw o WHERE o.product_id=pw.product_id AND o.quant-o.svl_qty<0) END),2) AS opt3_unit_cost, round(pw.svl_val - pw.flush_val,2) AS opt1_val_after FROM pw JOIN cls_a USING (product_id) JOIN product_product p ON p.id=pw.product_id JOIN stock_warehouse w ON w.id=pw.wh WHERE abs(pw.quant-pw.svl_qty)>.0001 ORDER BY 1,2) TO STDOUT WITH CSV HEADER
SQLEOF
)

PW_CMD='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"; PGOPTIONS="-c default_transaction_read_only=on" psql -h localhost -U odoo MOG_LIVE -q -v ON_ERROR_STOP=1'
printf '%s\n' "$SQL" | ssh mog-prod "$PW_CMD" > "$OUT"
printf '\xef\xbb\xbf' | cat - "$OUT" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
echo "rows: $(($(wc -l < "$OUT") - 1))  -> $OUT"
python3 -I - "$OUT" <<'PY'
import csv, sys, collections
r = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))
by = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
for x in r:
    a = by[x["product_code"]]
    a[0] += float(x["qty_delta"]); a[1] += float(x["opt1_value_delta"]); a[2] += float(x["opt2_value_delta"]); a[3] += float(x["opt3_value_delta"] or 0)
print("products:", len(by))
print("qty must net 0 per product:", all(abs(v[0]) < 1e-6 for v in by.values()))
print("opt1 total value change:", round(sum(v[1] for v in by.values()), 2))
print("opt2 total value change (should be ~0):", round(sum(v[2] for v in by.values()), 2))
print("opt3 total value change (should be ~0):", round(sum(v[3] for v in by.values()), 2))
print("opt3 basis:", dict(collections.Counter(x["opt3_basis"] for x in r)))
PY
