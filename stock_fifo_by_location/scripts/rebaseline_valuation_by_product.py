#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ปรับ "ยอดคงเหลือในรายงาน Stock FIFO Valuation" ของสินค้าให้ตรงกับที่ฝ่ายบัญชีนับ
(per product / per warehouse) โดยเพิ่ม stock.valuation.layer แค่ 1 แถวต่อรายการ

หลักการ (ตกลงกันแล้ว — ดู docs/fifo-valuation-rebaseline-plan.md §6a):
  layer ปรับ 1 แถว:
    quantity        = target_qty  - ยอดคงเหลือปัจจุบันในรายงาน   (Δqty)
    value           = target_value - มูลค่าคงเหลือปัจจุบันในรายงาน (Δvalue)
    unit_cost       ≈ |Δvalue / Δqty|      (ถ้า Δqty = 0 ให้ 0)
    remaining_qty   = 0
    remaining_value = 0                     <-- ไม่แตะ FIFO engine
    warehouse_id / current_warehouse_id = คลังนั้น
    accounting_date = วันปิดงวด (period_close) เดียวทั้ง run
    ไม่มี stock_move_id / ไม่มี account_move_id  <-- ไม่มี GL

ผล: รายงาน summary จะเลื่อน ending_qty / ending_value ไปเท่ากับที่บัญชีนับ
    - Δqty ที่ติดลบจะไปโผล่ในช่อง "จ่ายรวม" (out_qty) ของงวด — เป็นเรื่องปกติ
    - ยอด on-hand จริง (remaining_value_check) ไม่เปลี่ยน เพราะ remaining_* = 0
      (ถ้าต้องแก้ยอด on-hand สด ๆ ด้วย ต้องใช้ Phase 3 ของ rebaseline plan แทน)
    - ไม่แตะ system parameter stock_fifo_valuation_report.cutoff_date

สำคัญ: "ยอดปัจจุบัน" ต้องอ่านจาก summary wizard เท่านั้น ห้าม hand SQL
       (cutoff ถูกแปลง timezone แบบ Bangkok — hand SQL ที่ cast ::date จะได้เลขผิด)

วิธีใช้ (บน MOG_LIVE):
  0. pg_dump ก่อนเสมอ ถ้าจะรันจริง (dry_run=False) — ตาม policy
  1. เตรียม CSV: product_code,warehouse_code,target_qty,target_value,note
     (ดู rebaseline_valuation_template.csv)
  2. เปิด odoo shell แล้ว paste เนื้อไฟล์นี้ หรือ redirect เข้า stdin:
       python3 odoo-bin shell -c /etc/instance1.conf -d MOG_LIVE --no-http < rebaseline_valuation_by_product.py
     จากนั้นเรียก (dry-run อ่านอย่างเดียวก่อน):
       load_from_csv(env, '/tmp/rebaseline.csv', '2026-05-31', dry_run=True)
  3. ให้บัญชีเซ็นตารางกระทบยอด แล้วรันจริง:
       load_from_csv(env, '/tmp/rebaseline.csv', '2026-05-31', dry_run=False)
     (จะ backup ตาราง svl_bak_rebaseline_<date> + commit ทีละแถว +
      พิมพ์ list layer id ที่สร้าง + SQL rollback)
"""

import csv
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

QTY_TOL = 0.005
VAL_TOL = 0.01
DESC_PREFIX = "Re-baseline adjustment"


def _current_report_figures(env, product, warehouse_id, period_close):
    """ยอด ending_qty / ending_value ปัจจุบันในรายงาน summary (authoritative)."""
    wiz = env["stock.fifo.valuation.report.wizard"].create({
        "date_to": period_close,
        "product_ids": [(6, 0, product.ids)],
        "warehouse_ids": [(6, 0, [warehouse_id])],
    })
    env["stock.fifo.valuation.report"].init_results(wiz)
    rows = env["stock.fifo.valuation.report"].search([])
    if not rows:
        return 0.0, 0.0
    # กรอง product+warehouse แล้วเหลือแถวเดียว แต่กันไว้เผื่อ
    return sum(rows.mapped("ending_qty")), sum(rows.mapped("ending_value"))


def rebaseline_one(env, product_code, warehouse_code, target_qty, target_value,
                   period_close, dry_run=True):
    """สร้าง/ตรวจ layer ปรับ 1 แถว สำหรับสินค้า 1 ตัวใน 1 คลัง.

    return dict: {status, ...}
      status = 'skip_correct' | 'skip_adjusted' | 'dry_run' | 'applied' | 'error'
    """
    Product = env["product.product"]
    Warehouse = env["stock.warehouse"]
    SVL = env["stock.valuation.layer"]

    product = Product.search([("default_code", "=", product_code)], limit=1)
    if not product:
        return {"status": "error", "error": "ไม่พบสินค้า: %s" % product_code}
    warehouse = Warehouse.search([("code", "=", warehouse_code)], limit=1)
    if not warehouse:
        return {"status": "error", "error": "ไม่พบคลัง: %s" % warehouse_code}

    cur_qty, cur_val = _current_report_figures(
        env, product, warehouse.id, period_close)
    dqty = round(target_qty - cur_qty, 4)
    dval = round(target_value - cur_val, 2)

    base = {
        "product": product.display_name, "product_code": product_code,
        "warehouse": warehouse.name, "warehouse_code": warehouse_code,
        "cur_qty": cur_qty, "cur_val": cur_val,
        "target_qty": target_qty, "target_value": target_value,
        "dqty": dqty, "dval": dval, "product_id": product.id,
    }

    if abs(dqty) < QTY_TOL and abs(dval) < VAL_TOL:
        return dict(base, status="skip_correct")

    existing = SVL.search([
        ("product_id", "=", product.id),
        ("warehouse_id", "=", warehouse.id),
        ("accounting_date", ">=", "%s 00:00:00" % period_close),
        ("accounting_date", "<=", "%s 23:59:59" % period_close),
        ("description", "like", DESC_PREFIX + "%"),
    ], limit=1)
    if existing:
        return dict(base, status="skip_adjusted", layer_id=existing.id)

    if dry_run:
        return dict(base, status="dry_run")

    unit_cost = round(abs(dval / dqty), 4) if abs(dqty) >= QTY_TOL else 0.0
    desc = (
        "%s %s - finance count %s @ %s = %s (report was %s / %s)"
        % (DESC_PREFIX, period_close, target_qty,
           round(target_value / target_qty, 4) if target_qty else 0.0,
           round(target_value, 2), round(cur_qty, 4), round(cur_val, 2))
    )
    layer = SVL.create({
        "company_id": warehouse.company_id.id or product.company_id.id or 1,
        "product_id": product.id,
        "categ_id": product.categ_id.id,
        "quantity": dqty,
        "unit_cost": unit_cost,
        "value": dval,
        "remaining_qty": 0.0,
        "remaining_value": 0.0,
        "warehouse_id": warehouse.id,
        "current_warehouse_id": warehouse.id,
        "accounting_date": period_close,
        "description": desc,
    })
    env.cr.commit()

    v_qty, v_val = _current_report_figures(
        env, product, warehouse.id, period_close)
    ok = abs(v_qty - target_qty) < QTY_TOL and abs(v_val - target_value) < VAL_TOL
    return dict(base, status="applied", layer_id=layer.id,
                verify_qty=v_qty, verify_val=v_val,
                verify="PASS" if ok else "FAIL")


def load_from_csv(env, filepath, period_close, dry_run=True):
    """อ่าน CSV แล้วประมวลผลทุกแถว + พิมพ์ตารางกระทบยอด.

    CSV: product_code,warehouse_code,target_qty,target_value,note
    period_close: 'YYYY-MM-DD' (accounting_date ของ layer ปรับ — ค่าเดียวทั้ง run)
    """
    with open(filepath, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    mode = "DRY RUN (อ่านอย่างเดียว)" if dry_run else "LIVE (บันทึกจริง)"
    print("\n" + "=" * 100)
    print("Re-baseline Stock FIFO Valuation by product/warehouse")
    print("=" * 100)
    print("โหมด        : %s" % mode)
    print("วันปิดงวด    : %s" % period_close)
    print("ไฟล์         : %s  (%d รายการ)" % (filepath, len(rows)))
    print("เวลา         : %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("หมายเหตุ     : Δqty ติดลบจะเพิ่มยอด 'จ่ายรวม' ของงวด | ไม่มี GL — "
          "ผลรวม Σ Δvalue บัญชีต้องตั้งรายการปรับปรุงเอง")
    print("=" * 100)

    if not dry_run:
        pids = []
        for r in rows:
            p = env["product.product"].search(
                [("default_code", "=", r["product_code"].strip())], limit=1)
            if p:
                pids.append(p.id)
        tbl = "svl_bak_rebaseline_%s" % period_close.replace("-", "")
        env.cr.execute("SELECT to_regclass(%s)", (tbl,))
        if env.cr.fetchone()[0] is None and pids:
            env.cr.execute(
                "CREATE TABLE %s AS SELECT * FROM stock_valuation_layer "
                "WHERE product_id IN %%s" % tbl, (tuple(pids),))
            env.cr.commit()
            print("backup table: %s (%d products)" % (tbl, len(set(pids))))
        else:
            print("backup table: %s (มีอยู่แล้ว/ข้าม)" % tbl)

    results, made_ids = [], []
    sum_cur = sum_tgt = 0.0
    for idx, r in enumerate(rows, 1):
        try:
            res = rebaseline_one(
                env,
                r["product_code"].strip(),
                r["warehouse_code"].strip(),
                float(r["target_qty"]),
                float(r["target_value"]),
                period_close,
                dry_run=dry_run,
            )
        except Exception as e:  # noqa: BLE001
            res = {"status": "error", "error": str(e),
                   "product_code": r.get("product_code")}
        res["_row"] = idx
        results.append(res)
        if res["status"] == "applied":
            made_ids.append(res["layer_id"])
        if res["status"] in ("dry_run", "applied", "skip_correct", "skip_adjusted"):
            sum_cur += res.get("cur_val", 0.0)
            sum_tgt += res.get("target_value", 0.0)

    # ตารางกระทบยอด (CSV ไป stdout)
    print("\nrow,product_code,warehouse,status,cur_qty,cur_val,target_qty,"
          "target_value,dqty,dval,layer_id,verify")
    for res in results:
        if res["status"] == "error":
            print("%s,%s,,ERROR: %s,,,,,,,," %
                  (res["_row"], res.get("product_code", ""), res.get("error", "")))
            continue
        print("%s,%s,%s,%s,%.4f,%.2f,%.4f,%.2f,%.4f,%.2f,%s,%s" % (
            res["_row"], res["product_code"], res["warehouse_code"],
            res["status"], res["cur_qty"], res["cur_val"],
            res["target_qty"], res["target_value"], res["dqty"], res["dval"],
            res.get("layer_id", ""), res.get("verify", ""),
        ))
    print("TOTAL,,,,,%.2f,,%.2f,,%.2f,," %
          (sum_cur, sum_tgt, round(sum_tgt - sum_cur, 2)))

    n = {}
    for res in results:
        n[res["status"]] = n.get(res["status"], 0) + 1
    print("\nสรุป: " + " | ".join("%s=%d" % kv for kv in sorted(n.items())))

    if dry_run:
        print("\n⚠️  DRY RUN — ยังไม่บันทึก")
    elif made_ids:
        print("\n✅ สร้าง layer: %s" % made_ids)
        print("rollback SQL: DELETE FROM stock_valuation_layer WHERE id IN (%s);"
              % ", ".join(str(i) for i in made_ids))
        fails = [r for r in results if r.get("verify") == "FAIL"]
        if fails:
            print("❌ VERIFY FAIL %d รายการ — ตรวจสอบ: %s"
                  % (len(fails), [r["product_code"] for r in fails]))
    print("=" * 100 + "\n")
    return results


if __name__ != "__main__":
    print("\n✅ โหลด rebaseline_valuation_by_product เรียบร้อย")
    print("   load_from_csv(env, '/tmp/rebaseline.csv', '2026-05-31', dry_run=True)")
    print("   rebaseline_one(env, 'FCA0006100', 'FG10', 217, 78956.23, '2026-05-31', dry_run=True)")
