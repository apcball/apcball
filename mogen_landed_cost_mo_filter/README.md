# Mogen Landed Cost MO Filter

ตัวช่วยค้นหา Manufacturing Orders จากหน้า Stock Landed Cost โดยใช้ Analytic Account, ช่วงวันที่ และสถานะ MO โมดูลนี้เขียนเฉพาะฟิลด์ `stock.landed.cost.mrp_production_ids` เดิม และไม่เปลี่ยนการคำนวณต้นทุน การตีมูลค่าสต็อก หรือการลงบัญชี

## Detected configuration

- MO field: `mrp_production_ids` (Many2many → `mrp.production`)
- Analytic field: `analytic_account_ids` (Many2many → `account.analytic.account`)
- Date field: `date_finished` (Datetime)
- Form view: `mrp_landed_costs.view_mrp_landed_costs_form`

## Dependencies and installation

Dependencies are `mrp_landed_costs` and `analytic`. Copy this directory to the custom addons path, update the Apps list, and install **Mogen Landed Cost MO Filter**. For an upgrade:

```bash
odoo -d <database> -u mogen_landed_cost_mo_filter --stop-after-init --no-http
```

## Usage

On a draft Landed Cost with target **Manufacturing**, select an Analytic Account, date range, and MO status, then click **Search Manufacturing Orders**. Search respects the current user's `mrp.production` access rights.

**Replace Existing MOs** replaces the existing selection only when results are found. **Add to Existing MOs** preserves existing records and adds matching MOs without duplicates. A no-result search leaves the existing selection unchanged and shows a warning.

The helper uses `date_finished` as a timezone-aware Datetime range. It does not override standard landed-cost compute, validation, valuation-layer, cost-split, or journal-entry methods. The repository DEV database had no Analytic Group field on `mrp.production`; therefore this implementation uses the existing Analytic Account field.
