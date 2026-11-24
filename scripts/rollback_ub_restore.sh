#!/usr/bin/env bash
# Targeted ROLLBACK of scripts/fix_restore_ub_components.sh (used 2026-11-09 12:57 to undo the apply of 12:52; do NOT restore whole tables
# from the dump - that would overwrite business transactions made since). It reverses exactly the moves touched by that apply:
#   * moves = UB/% done moves with write_date inside [FROM, TO) (UTC) whose quantity == product_qty (the restored ones)
#   * the deleted "Correction of ..." SVL layers are re-inserted from the pre-apply dump (same ids / columns)
#   * move line + move quantity back to 0; stock_quant at the destination -= restored qty; quants created in the window and left at 0 are deleted
# Usage: scripts/rollback_ub_restore.sh test|apply DUMP_FILE_ON_MOG_PROD 'YYYY-MM-DD HH:MI' 'YYYY-MM-DD HH:MI'
#   e.g. scripts/rollback_ub_restore.sh test /home/mogenit/db_backups/ub_restore_20261109_125229.dump '2026-11-09 05:50' '2026-11-09 05:55'
# test = everything executed inside a transaction that is rolled back. apply = takes a fresh backup then COMMITs.
set -euo pipefail
MODE="${1:-}"; DUMP="${2:-}"; FROM="${3:-}"; TO="${4:-}"
case "$MODE" in test|apply) ;; *) echo "usage: $0 test|apply DUMP 'FROM' 'TO'" >&2; exit 2;; esac
[ -n "$DUMP" ] && [ -n "$FROM" ] && [ -n "$TO" ] || { echo "need DUMP FROM TO" >&2; exit 2; }
for v in "$DUMP" "$FROM" "$TO"; do [[ "$v" =~ ^[A-Za-z0-9_./:\ -]+$ ]] || { echo "bad argument" >&2; exit 2; }; done
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
python3 - "$DUMP" "$FROM" "$TO" "$WORK" <<'PYEOF'
import subprocess, re, sys
dump, frm, to, work = sys.argv[1:5]
ssh = lambda cmd: subprocess.run(['ssh', 'mog-prod', cmd], capture_output=True, text=True, check=True)
q = ("select id from stock_move where reference like 'UB/%' and write_date>='%s' and write_date<'%s' and state='done' and product_qty>0 and quantity=product_qty "
     "and id in (select move_id from stock_move_line where write_date>='%s' and write_date<'%s') order by id;" % (frm, to, frm, to))
ids = [int(x) for x in ssh('PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"; PGOPTIONS="-c default_transaction_read_only=on" psql -h localhost -U odoo MOG_LIVE -q -A -t -c "%s"' % q.replace('"', '\\"')).stdout.split()]
txt = ssh('pg_restore -t stock_valuation_layer -f - %s' % dump).stdout
m = re.search(r'COPY public\.stock_valuation_layer \(([^)]*)\) FROM stdin;\n', txt)
cols = [c.strip() for c in m.group(1).split(',')]
body = txt[m.end():]; rows = body[:body.index('\n\\.\n')].split('\n')
iM, iD = cols.index('stock_move_id'), cols.index('description')
idset = set(ids)
sel = [r.split('\t') for r in rows if len(r.split('\t')) == len(cols) and r.split('\t')[iM] != '\\N' and int(r.split('\t')[iM]) in idset and r.split('\t')[iD].startswith('Correction of')]
open(work + '/ids', 'w').write(','.join(map(str, ids)))
with open(work + '/layers.copy', 'w') as o:
    o.write('COPY stock_valuation_layer (%s) FROM stdin;\n' % ', '.join(cols))
    for f in sel: o.write('\t'.join(f) + '\n')
    o.write('\\.\n')
print('moves', len(ids), 'correction layers to restore', len(sel))
if not ids or len(sel) < len(ids): sys.exit('layer/move count mismatch')
PYEOF
IDS="$(cat "$WORK/ids")"; N=$(tr ',' '\n' < "$WORK/ids" | wc -l | tr -d ' ')
cat > "$WORK/run.sql" <<SQL
CREATE TEMP TABLE rb AS SELECT id, product_id pid, location_dest_id ldst, product_qty q FROM stock_move WHERE id IN ($IDS);
DO \$\$ BEGIN
  IF (SELECT count(*) FROM rb)<>$N THEN RAISE EXCEPTION 'move count mismatch'; END IF;
  IF (SELECT count(*) FROM stock_valuation_layer l WHERE l.stock_move_id IN (SELECT id FROM rb) AND l.description LIKE 'Correction of%')<>0 THEN RAISE EXCEPTION 'correction layers already present'; END IF;
END \$\$;
CREATE TEMP TABLE dq AS SELECT pid, ldst, sum(q) delta FROM rb GROUP BY 1,2;
DO \$\$ BEGIN
  IF EXISTS (SELECT 1 FROM dq WHERE coalesce((SELECT sum(quantity) FROM stock_quant x WHERE x.product_id=dq.pid AND x.location_id=dq.ldst),0) < dq.delta - 0.0001) THEN RAISE EXCEPTION 'quant at a destination no longer covers the restored qty (consumed since)'; END IF;
END \$\$;
$(cat "$WORK/layers.copy")
UPDATE stock_move_line SET quantity=0, quantity_product_uom=0, write_date=now() AT TIME ZONE 'UTC' WHERE move_id IN (SELECT id FROM rb);
UPDATE stock_move SET quantity=0, write_date=now() AT TIME ZONE 'UTC' WHERE id IN (SELECT id FROM rb);
UPDATE stock_quant q SET quantity=q.quantity-dq.delta, write_date=now() AT TIME ZONE 'UTC' FROM dq WHERE q.product_id=dq.pid AND q.location_id=dq.ldst AND q.id=(SELECT min(id) FROM stock_quant x WHERE x.product_id=dq.pid AND x.location_id=dq.ldst);
DELETE FROM stock_quant WHERE create_date>='$FROM' AND create_date<'$TO' AND quantity=0 AND reserved_quantity=0 AND (product_id,location_id) IN (SELECT pid, ldst FROM dq);
SELECT (SELECT count(*) FROM stock_valuation_layer l WHERE l.stock_move_id IN (SELECT id FROM rb) AND l.description LIKE 'Correction of%') correction_layers,
       (SELECT count(*) FROM stock_move_line ml WHERE ml.move_id IN (SELECT id FROM rb) AND ml.quantity<>0) nonzero_lines,
       (SELECT count(*) FROM stock_quant WHERE quantity<0 AND (product_id,location_id) IN (SELECT pid, ldst FROM dq)) negative_quants;
SQL
if [ "$MODE" = test ]; then END=ROLLBACK; else
  STAMP=$(date +%Y%m%d_%H%M%S)
  ssh mog-prod "$REMOTE_ENV; pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line -t stock_valuation_layer -t stock_quant MOG_LIVE -f ~/db_backups/ub_restore_before_rollback_${STAMP}.dump && ls -l ~/db_backups/ub_restore_before_rollback_${STAMP}.dump"
  END=COMMIT
fi
{ echo 'BEGIN;'; cat "$WORK/run.sql"; echo "$END;"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($END)"
