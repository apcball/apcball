#!/bin/bash
# READ-ONLY (shell session rolled back). Compare buz_new_stock_card (NEW code from a scratch addons dir, ahead of the
# installed one in addons_path) with the real Imex report on prod MOG_LIVE, per (product, location), window
# DATE_FROM..today. Also prints what the OLD ledger opening would have been.
# Usage: bash stockcard_vs_imex_compare.sh "MO010S101,403030003,FCA0006100" [N_RANDOM]
CODES="${1:-MO010S101,403030003,FCA0006100}"
NRAND="${2:-40}"
DATE_FROM="${DATE_FROM:-2026-03-30}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/buz_new_stock_card"
rsync -a --delete --exclude __pycache__ "$SRC/" mog-prod:/tmp/sc_addons/buz_new_stock_card/ || exit 1
ssh mog-prod "chmod -R a+rX /tmp/sc_addons; cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate && \
 CODES='$CODES' NRAND='$NRAND' DATE_FROM='$DATE_FROM' python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http \
 --addons-path=/tmp/sc_addons,/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons --log-level=error 2>&1" <<'PYEOF' | grep -E "^(ROW|SUM|PATH|ERR)"
import os, random
from odoo import fields
env = env(user=2)
cr = env.cr
import odoo.addons.buz_new_stock_card.models.stock_card_report as m
print("PATH", m.__file__)
codes = [c for c in os.environ["CODES"].split(",") if c]
products = env["product.product"].search([("default_code", "in", codes)])
nrand = int(os.environ["NRAND"])
if nrand:
    cr.execute("""select distinct q.product_id from stock_quant q join stock_location l on l.id=q.location_id
                  where l.usage='internal' and q.quantity<>0""")
    ids = [r[0] for r in cr.fetchall()]
    random.seed(7)
    products |= env["product.product"].browse(random.sample(ids, min(nrand, len(ids))))
date_from = os.environ["DATE_FROM"]
date_to = str(fields.Date.context_today(env["res.users"]))
wiz = env["imex.inventory.report.wizard"].create({
    "date_from": date_from, "date_to": date_to, "product_ids": [(6, 0, products.ids)],
    "is_groupby_location": True,
})
env["imex.inventory.report"].init_results(wiz)
rows = env["imex.inventory.report"].search([("product_id", "in", products.ids)])
eng = env["buz.stock.card.report"]
start_utc, _ = eng._date_range_utc(date_from, date_to)
company_ids = env.companies.ids
bad = n = 0
for r in rows:
    loc = r.location
    loc_id = loc.id if hasattr(loc, "id") else int(loc)
    if hasattr(loc, "usage") and loc.usage not in ("internal",):
        continue
    d = eng.get_stock_card_data(r.product_id.id, [loc_id], date_from, date_to, page_size=1, page=0, company_ids=company_ids)
    old_dom = [("state","=","done"),("product_id","=",r.product_id.id),("date","<",start_utc),("company_id","in",company_ids)] + eng._scope_domain([loc_id])
    old = sum(a - b for l in eng._read_lines_with_base_qty(old_dom) for a, b in [eng._direction_qty(l, [loc_id])])
    ok_o = abs(d["opening_balance"] - r.initial) < 1e-6
    ok_c = abs(d["closing_balance"] - r.balance) < 1e-6
    n += 1
    if not (ok_o and ok_c): bad += 1
    if (not (ok_o and ok_c)) or abs(old - r.initial) > 1e-6:
        print("ROW", r.product_id.default_code, loc.complete_name if hasattr(loc, "complete_name") else loc_id,
              "imex_open=%s card_open_NEW=%s card_open_OLD=%s imex_close=%s card_close_NEW=%s %s" % (
              r.initial, d["opening_balance"], old, r.balance, d["closing_balance"], "OK" if ok_o and ok_c else "MISMATCH"))
print("SUM rows=%d mismatch_new=%d" % (n, bad))
env.cr.rollback()
PYEOF
