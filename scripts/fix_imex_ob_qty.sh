#!/usr/bin/env bash
# imex rule (user, 2026-11-05): the opening balance IS the MOGEN_OB reseed pickings (2026-03-31 00:55); everything BEFORE
# them must be 0. So the Initial plugs are fixed IN the OB documents, not by extra rows before them:
#   +n on the OB move/move line at the location that physically holds the unit (Initial +n),
#   -n on the OB move/move line at the location that was over-counted (Initial -n).
# Only stock_move.product_uom_qty/product_qty/quantity and stock_move_line.quantity/quantity_product_uom change, on the
# LARGEST single OB line of that product at that location. quants, SVL layers (OB layers, flush-pair / G1 / G2 layers),
# FIFO queue and journal entries are NOT touched (the SVL ledger of these products was already corrected by plain layers).
#
# 15 pairs: those where both locations have an OB line and the over-counted line has >= n. NOT included (need a new OB
# line or are not an OB error): 406010069 (PD01 has no OB line), MA0142101 (FG10 has none), 404030004 (RM03/QTL has none),
# 60101040145 (no OB lines), MU0002101 (FG40 has none).
# Products that currently carry G2 SVL layers (403030003, FCA*) keep them (they sit at 00:00, before OB): decide that
# with accounting separately.
#
# Modes: check (preconditions, rolls back) | dry (backup, update + post-checks, ROLLBACK) | apply (COMMIT)
# Optional 2nd arg: comma list of product codes to limit the run. dry/apply print the exact reverse UPDATE statements.
set -euo pipefail
MODE="${1:-check}"
ONLY="${2:-}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply [code1,code2]" >&2; exit 2;; esac
if [ -n "$ONLY" ] && ! [[ "$ONLY" =~ ^[A-Za-z0-9,._+-]+$ ]]; then echo "bad list" >&2; exit 2; fi
FILTER=""; [ -n "$ONLY" ] && FILTER="DELETE FROM pr WHERE code <> ALL(string_to_array('$ONLY',','));"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE pr(code text, loc_in int, loc_out int, n numeric);
INSERT INTO pr VALUES
 ('301010008',92,116,40),('401020002',92,116,1),('403030003',116,1205,12),('409110001',92,116,4),('409250055',92,116,160),
 ('FCA0003100',8,1201,3),('FCA0006100',8,1201,1),('FCA0025100',8,1201,1),('FCA0045100',8,1201,1),('FCA0065100',8,1201,1),
 ('FCA0248120',8,1201,1),('FU0033FC1560',8,76,1),('MA332B1101',8,76,1),('MO006901110',8,76,1),('SPW031100',1220,8,1);
@@FILTER@@
CREATE TEMP TABLE obl AS
SELECT ml.id mlid, ml.move_id, ml.product_id pid, ml.location_dest_id lid, ml.quantity q, ml.quantity_product_uom qpu
FROM stock_move_line ml JOIN stock_picking pk ON pk.id=ml.picking_id JOIN res_partner pt ON pt.id=pk.partner_id
WHERE ml.state='done' AND ml.date>='2026-03-31 00:50' AND ml.date<'2026-03-31 01:00' AND pt.name='MOGEN_OB'
  AND ml.reference NOT LIKE 'IMEX%'
  AND ml.product_id IN (SELECT id FROM product_product WHERE default_code IN (SELECT code FROM pr));
CREATE TEMP TABLE st AS
SELECT pr.*, p.id pid, (SELECT count(*) FROM product_product x WHERE x.default_code=pr.code) n_prod,
 (SELECT mlid FROM obl WHERE pid=p.id AND lid=pr.loc_in ORDER BY q DESC, mlid LIMIT 1) in_ml,
 (SELECT mlid FROM obl WHERE pid=p.id AND lid=pr.loc_out AND q>=pr.n ORDER BY q DESC, mlid LIMIT 1) out_ml,
 (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q WHERE q.product_id=p.id AND q.location_id=pr.loc_in) q_in,
 (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q WHERE q.product_id=p.id AND q.location_id=pr.loc_out) q_out,
 (SELECT count(*) FROM stock_move WHERE product_id=p.id AND reference='IMEX-OPENING-20260331') opening_left
FROM pr JOIN product_product p ON p.default_code=pr.code;
ALTER TABLE st ADD COLUMN net_in numeric, ADD COLUMN net_out numeric;
UPDATE st s SET
 net_in = (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_in THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_in THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_in OR ml.location_id=s.loc_in)),
 net_out = (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_out THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_out THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_out OR ml.location_id=s.loc_out));
\echo '== preconditions that FAIL (expect none): Initial(in)=+n, Initial(out)=-n, OB lines found with qty==qty_product_uom, no opening moves left'
SELECT s.code, s.n, q_in-net_in init_in, q_out-net_out init_out, in_ml, out_ml, opening_left FROM st s
 WHERE n_prod<>1 OR q_in-net_in<>n OR q_out-net_out<>-n OR in_ml IS NULL OR out_ml IS NULL OR opening_left<>0
    OR EXISTS (SELECT 1 FROM obl WHERE mlid IN (s.in_ml,s.out_ml) AND q<>qpu);
DO $$
DECLARE bad int;
BEGIN
  IF (SELECT count(*) FROM st)<>(SELECT count(*) FROM pr) OR (SELECT count(*) FROM st)=0 THEN RAISE EXCEPTION 'pair list mismatch'; END IF;
  SELECT count(*) INTO bad FROM st s WHERE n_prod<>1 OR q_in-net_in<>n OR q_out-net_out<>-n OR in_ml IS NULL OR out_ml IS NULL OR opening_left<>0
    OR EXISTS (SELECT 1 FROM obl WHERE mlid IN (s.in_ml,s.out_ml) AND q<>qpu);
  IF bad<>0 THEN RAISE EXCEPTION 'precondition failed on % pairs', bad; END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE qsum AS SELECT round(sum(quantity),4) q FROM stock_quant WHERE product_id IN (SELECT pid FROM st);
CREATE TEMP TABLE svlsum AS SELECT count(*) c, round(sum(value)::numeric,2) v, round(sum(quantity),4) q FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM st);
CREATE TEMP TABLE chg AS
 SELECT in_ml mlid, n delta FROM st UNION ALL SELECT out_ml, -n FROM st;
\echo '== reverse statements (save these):'
SELECT format('UPDATE stock_move_line SET quantity=quantity-(%s), quantity_product_uom=quantity_product_uom-(%s) WHERE id=%s; UPDATE stock_move SET product_uom_qty=product_uom_qty-(%s), product_qty=product_qty-(%s), quantity=quantity-(%s) WHERE id=(SELECT move_id FROM stock_move_line WHERE id=%s);', c.delta, c.delta, c.mlid, c.delta, c.delta, c.delta, c.mlid) AS reverse_sql FROM chg c ORDER BY c.mlid;
UPDATE stock_move m SET product_uom_qty=m.product_uom_qty+c.delta, product_qty=m.product_qty+c.delta, quantity=m.quantity+c.delta, write_date=now() AT TIME ZONE 'UTC'
 FROM chg c JOIN stock_move_line ml ON ml.id=c.mlid WHERE m.id=ml.move_id;
UPDATE stock_move_line ml SET quantity=ml.quantity+c.delta, quantity_product_uom=ml.quantity_product_uom+c.delta, write_date=now() AT TIME ZONE 'UTC'
 FROM chg c WHERE ml.id=c.mlid;
\echo '== post-check rows that FAIL (expect none): Initial 0 at both locations'
SELECT s.code, s.q_in - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_in THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_in THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_in OR ml.location_id=s.loc_in)) init_in,
       s.q_out - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_out THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_out THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_out OR ml.location_id=s.loc_out)) init_out
FROM st s WHERE abs(s.q_in - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_in THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_in THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_in OR ml.location_id=s.loc_in)))>0.0001
   OR abs(s.q_out - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_out THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_out THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_out OR ml.location_id=s.loc_out)))>0.0001;
DO $$
DECLARE bad int; q2 numeric; c2 int; v2 numeric; s2 numeric; mv_bad int;
BEGIN
  SELECT count(*) INTO bad FROM st s WHERE
    abs(s.q_in - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_in THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_in THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_in OR ml.location_id=s.loc_in)))>0.0001
    OR abs(s.q_out - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_out THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_out THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_out OR ml.location_id=s.loc_out)))>0.0001;
  SELECT count(*) INTO mv_bad FROM chg c JOIN stock_move_line ml ON ml.id=c.mlid JOIN stock_move m ON m.id=ml.move_id WHERE m.quantity<>ml.quantity OR m.product_qty<>ml.quantity OR ml.quantity<>ml.quantity_product_uom OR ml.quantity<0;
  SELECT round(sum(quantity),4) INTO q2 FROM stock_quant WHERE product_id IN (SELECT pid FROM st);
  SELECT count(*), round(sum(value)::numeric,2), round(sum(quantity),4) INTO c2, v2, s2 FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM st);
  IF bad<>0 OR mv_bad<>0 OR q2 IS DISTINCT FROM (SELECT q FROM qsum) OR c2<>(SELECT c FROM svlsum) OR v2 IS DISTINCT FROM (SELECT v FROM svlsum) OR s2 IS DISTINCT FROM (SELECT q FROM svlsum) THEN
    RAISE EXCEPTION 'post-check failed: bad %, move/line mismatch %, quant %, svl % / % / %', bad, mv_bad, q2, c2, v2, s2;
  END IF;
  RAISE NOTICE 'post-check ok: % pairs, all Initial rows are 0, OB docs edited, quants and SVL unchanged', (SELECT count(*) FROM st);
END $$;
SQLEOF
)
BODY="${BODY//@@FILTER@@/$FILTER}"

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  echo "== check ok (no failing rows listed above)"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move + stock_move_line on mog-prod (~/db_backups/imex_ob_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/imex_ob_${STAMP}.dump && ls -l ~/db_backups/imex_ob_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
