#!/usr/bin/env bash
# OBSOLETE (2026-11-09): user confirmed the MOGEN_OB amounts are CORRECT; Initial plugs must NOT be fixed by editing/adding OB lines or rows before the OB.
# The OB edits applied on 2026-11-05 were reverted on 2026-11-09. DO NOT RUN. Kept only for history.
# imex "Initial" must be 0 before the cut-off (user rule 2026-11-05): add ONE done internal move + ONE move line per
# mirrored pair of Initial plugs, dated 2026-03-31 00:00 UTC (before the 00:55 reseed/OB pickings), reference
# IMEX-OPENING-20260331. Option A of the imex-plug discussion: no change to quants, no new SVL (the G1/G2/flush-pair
# SVL layers already carry the same unit), old documents untouched.
#
# imex Initial per (product, location) = quant - net done move lines since 2026-03-30 17:00 UTC. For the 20 products below
# the plugs are exact mirrors (+n at the location that physically holds the unit, -n at the location that does not),
# so one move out of the "-n" location into the "+n" location zeroes both.
#
# Left out on purpose: group B (402010001, 60104010008, 60104010010 = need physical count) and group E / one-sided plugs.
#
# Optional 2nd arg ONLY=code1,code2 limits the run to those products (e.g. a first pilot on FCA0006100).
# Modes: check (preconditions, rolls back) | dry (backup stock_move + stock_move_line, insert + post-checks, ROLLBACK) | apply (COMMIT)
# Rollback after apply (all): DELETE FROM stock_move_line WHERE reference='IMEX-OPENING-20260331'; DELETE FROM stock_move WHERE reference='IMEX-OPENING-20260331';
# (one product: add AND product_id=(SELECT id FROM product_product WHERE default_code='<code>'))
set -euo pipefail
MODE="${1:-check}"
ONLY="${2:-}"
case "$MODE" in check|dry|apply) ;; *) echo "usage: $0 check|dry|apply" >&2; exit 2;; esac
if [ -n "$ONLY" ] && ! [[ "$ONLY" =~ ^[A-Za-z0-9,._+-]+$ ]]; then echo "bad ONLY list" >&2; exit 2; fi
FILTER=""
[ -n "$ONLY" ] && FILTER="DELETE FROM pr WHERE code <> ALL(string_to_array('$ONLY',','));"
REMOTE_ENV='PW=$(grep -E "^db_password" /etc/instance1.conf); export PGPASSWORD="${PW#*= }"'

BODY=$(cat <<'SQLEOF'
CREATE TEMP TABLE pr(code text, loc_in int, loc_out int, n numeric);
INSERT INTO pr VALUES
 ('301010008',92,116,40),('401020002',92,116,1),('403030003',116,1205,12),('404030004',116,1187,35),
 ('406010069',92,116,200),('409110001',92,116,4),('409250055',92,116,160),('60101040145',92,116,17),
 ('FCA0003100',8,1201,3),('FCA0006100',8,1201,1),('FCA0025100',8,1201,1),('FCA0045100',8,1201,1),
 ('FCA0065100',8,1201,1),('FCA0248120',8,1201,1),('FU0033FC1560',8,76,1),('MA0142101',8,76,2),
 ('MA332B1101',8,76,1),('MO006901110',8,76,1),('MU0002101',68,76,1),('SPW031100',1220,8,1);
@@FILTER@@
CREATE TEMP TABLE st AS
SELECT pr.*, p.id pid, (SELECT count(*) FROM product_product x WHERE x.default_code=pr.code) n_prod,
 (SELECT t.uom_id FROM product_template t WHERE t.id=p.product_tmpl_id) uom,
 (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q WHERE q.product_id=p.id AND q.location_id=pr.loc_in) q_in,
 (SELECT coalesce(sum(q.quantity),0) FROM stock_quant q WHERE q.product_id=p.id AND q.location_id=pr.loc_out) q_out,
 (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=pr.loc_in THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=pr.loc_in THEN ml.quantity ELSE 0 END),0)
    FROM stock_move_line ml WHERE ml.product_id=p.id AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=pr.loc_in OR ml.location_id=pr.loc_in)) net_in,
 (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=pr.loc_out THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=pr.loc_out THEN ml.quantity ELSE 0 END),0)
    FROM stock_move_line ml WHERE ml.product_id=p.id AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=pr.loc_out OR ml.location_id=pr.loc_out)) net_out,
 (SELECT count(*) FROM stock_move WHERE product_id=p.id AND reference='IMEX-OPENING-20260331') done
FROM pr JOIN product_product p ON p.default_code=pr.code;
\echo '== preconditions: Initial(in) = +n and Initial(out) = -n, not yet applied (rows shown only when they FAIL)'
SELECT code, loc_in, q_in, net_in, q_in-net_in init_in, loc_out, q_out, net_out, q_out-net_out init_out, n, done FROM st
 WHERE n_prod<>1 OR q_in-net_in<>n OR q_out-net_out<>-n OR done<>0;
DO $$
DECLARE bad int;
BEGIN
  IF (SELECT count(*) FROM st)<>(SELECT count(*) FROM pr) OR (SELECT count(*) FROM st)=0 THEN RAISE EXCEPTION 'pair list mismatch'; END IF;
  SELECT count(*) INTO bad FROM st WHERE n_prod<>1 OR q_in-net_in<>n OR q_out-net_out<>-n OR done<>0;
  IF bad<>0 THEN RAISE EXCEPTION 'precondition failed on % pairs', bad; END IF;
END $$;
SQLEOF
)

WRITE=$(cat <<'SQLEOF'
CREATE TEMP TABLE qsum AS SELECT round(sum(quantity),4) q FROM stock_quant WHERE product_id IN (SELECT pid FROM st);
CREATE TEMP TABLE svlsum AS SELECT count(*) c, round(sum(value)::numeric,2) v FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM st);
DO $$
DECLARE r record; mid int;
BEGIN
  FOR r IN SELECT * FROM st ORDER BY code LOOP
    DROP TABLE IF EXISTS m; DROP TABLE IF EXISTS l;
    CREATE TEMP TABLE m AS SELECT * FROM stock_move WHERE id=332738;
    UPDATE m SET id = nextval(pg_get_serial_sequence('stock_move','id')), product_id = r.pid, product_uom = r.uom,
      name = 'IMEX opening plug ' || r.code || ' ' || r.n || ' (pre-cutoff stock, 2026-03-31 00:00)',
      reference = 'IMEX-OPENING-20260331', location_id = r.loc_out, location_dest_id = r.loc_in,
      product_qty = r.n, product_uom_qty = r.n, quantity = r.n, picked = true, state = 'done',
      date = TIMESTAMP '2026-03-31 00:00:00', weight = coalesce((SELECT weight FROM product_product WHERE id=r.pid),0) * r.n,
      backdate_remark = 'imex opening plug 2026-11-05', create_date = now() AT TIME ZONE 'UTC', write_date = now() AT TIME ZONE 'UTC';
    INSERT INTO stock_move SELECT * FROM m;
    SELECT id INTO mid FROM m;
    CREATE TEMP TABLE l AS SELECT * FROM stock_move_line WHERE id=341226;
    UPDATE l SET id = nextval(pg_get_serial_sequence('stock_move_line','id')), move_id = mid, picking_id = NULL,
      product_id = r.pid, product_uom_id = r.uom, location_id = r.loc_out, location_dest_id = r.loc_in,
      quantity = r.n, quantity_product_uom = r.n, state = 'done', reference = 'IMEX-OPENING-20260331', picked = true,
      date = TIMESTAMP '2026-03-31 00:00:00', lot_id = NULL, package_id = NULL, result_package_id = NULL, owner_id = NULL,
      description_picking = NULL, batch_id = NULL, workorder_id = NULL, production_id = NULL,
      create_date = now() AT TIME ZONE 'UTC', write_date = now() AT TIME ZONE 'UTC';
    INSERT INTO stock_move_line SELECT * FROM l;
    DROP TABLE m; DROP TABLE l;
  END LOOP;
END $$;
\echo '== post-check rows that FAIL (expect none): Initial(in)=0 and Initial(out)=0 at both locations'
SELECT code, loc_in, loc_out,
 q_in - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=st.loc_in THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=st.loc_in THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=st.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=st.loc_in OR ml.location_id=st.loc_in)) init_in,
 q_out - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=st.loc_out THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=st.loc_out THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=st.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=st.loc_out OR ml.location_id=st.loc_out)) init_out
FROM st WHERE abs(q_in - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=st.loc_in THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=st.loc_in THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=st.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=st.loc_in OR ml.location_id=st.loc_in)))>0.0001
   OR abs(q_out - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=st.loc_out THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=st.loc_out THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=st.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=st.loc_out OR ml.location_id=st.loc_out)))>0.0001;
DO $$
DECLARE bad int; nm int; nl int; q2 numeric; c2 int; v2 numeric;
BEGIN
  SELECT count(*) INTO bad FROM st s WHERE
    abs(s.q_in - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_in THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_in THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_in OR ml.location_id=s.loc_in)))>0.0001
    OR abs(s.q_out - (SELECT coalesce(sum(CASE WHEN ml.location_dest_id=s.loc_out THEN ml.quantity ELSE 0 END)-sum(CASE WHEN ml.location_id=s.loc_out THEN ml.quantity ELSE 0 END),0) FROM stock_move_line ml WHERE ml.product_id=s.pid AND ml.state='done' AND ml.date>='2026-03-30 17:00' AND (ml.location_dest_id=s.loc_out OR ml.location_id=s.loc_out)))>0.0001;
  SELECT count(*) INTO nm FROM stock_move WHERE reference='IMEX-OPENING-20260331';
  SELECT count(*) INTO nl FROM stock_move_line WHERE reference='IMEX-OPENING-20260331';
  SELECT round(sum(quantity),4) INTO q2 FROM stock_quant WHERE product_id IN (SELECT pid FROM st);
  SELECT count(*), round(sum(value)::numeric,2) INTO c2, v2 FROM stock_valuation_layer WHERE product_id IN (SELECT pid FROM st);
  IF bad<>0 OR nm<>(SELECT count(*) FROM st) OR nl<>(SELECT count(*) FROM st) OR q2 IS DISTINCT FROM (SELECT q FROM qsum) OR c2<>(SELECT c FROM svlsum) OR v2 IS DISTINCT FROM (SELECT v FROM svlsum) THEN
    RAISE EXCEPTION 'post-check failed: bad %, moves %, lines %, quant % vs %, svl % / % vs % / %', bad, nm, nl, q2, (SELECT q FROM qsum), c2, v2, (SELECT c FROM svlsum), (SELECT v FROM svlsum);
  END IF;
  RAISE NOTICE 'post-check ok: % moves, % lines, all Initial rows of those pairs are 0, quants and SVL unchanged', nm, nl;
END $$;
SQLEOF
)

BODY="${BODY//@@FILTER@@/$FILTER}"

if [ "$MODE" = check ]; then
  { printf 'BEGIN;\n%s\nROLLBACK;\n' "$BODY"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
  echo "== check ok (no rows listed above = all 20 pairs match their expected plugs)"
  exit 0
fi
COMMIT_OR_ROLLBACK=$([ "$MODE" = apply ] && echo COMMIT || echo ROLLBACK)
STAMP=$(date +%Y%m%d_%H%M%S)
echo ">>> backup stock_move + stock_move_line on mog-prod (~/db_backups/imex_open_${STAMP}.dump)"
ssh mog-prod "$REMOTE_ENV; mkdir -p ~/db_backups && pg_dump -h localhost -U odoo -Fc -t stock_move -t stock_move_line MOG_LIVE -f ~/db_backups/imex_open_${STAMP}.dump && ls -l ~/db_backups/imex_open_${STAMP}.dump"
{ printf 'BEGIN;\n%s\n%s\n%s;\n' "$BODY" "$WRITE" "$COMMIT_OR_ROLLBACK"; } | ssh mog-prod "$REMOTE_ENV; psql -h localhost -U odoo MOG_LIVE -v ON_ERROR_STOP=1 -q"
echo ">>> $MODE finished ($COMMIT_OR_ROLLBACK)"
