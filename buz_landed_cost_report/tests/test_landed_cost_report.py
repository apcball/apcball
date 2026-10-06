from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestLandedCostReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        categ = cls.env['product.category'].create({
            'name': 'LC Test Categ',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'LC Test Product',
            'type': 'product',
            'categ_id': categ.id,
            'standard_price': 0.0,
        })
        cls.service = cls.env['product.product'].create({
            'name': 'LC Test Freight',
            'type': 'service',
            'landed_cost_ok': True,
            'split_method_landed_cost': 'by_quantity',
        })
        wh = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.picking = cls.env['stock.picking'].create({
            'picking_type_id': wh.in_type_id.id,
            'location_id': cls.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': wh.lot_stock_id.id,
            'move_ids': [(0, 0, {
                'name': 'LC test move',
                'product_id': cls.product.id,
                'product_uom_qty': 10,
                'product_uom': cls.product.uom_id.id,
                'price_unit': 100.0,
                'location_id': cls.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': wh.lot_stock_id.id,
            })],
        })
        cls.picking.action_confirm()
        cls.picking.move_ids.quantity = 10
        cls.picking.move_ids.picked = True
        cls.picking._action_done()

    def _make_lc(self, amounts):
        journal = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.company.id)], limit=1)
        expense = self.env['account.account'].search(
            [('account_type', '=', 'expense'), ('company_id', '=', self.company.id)], limit=1)
        lc = self.env['stock.landed.cost'].create({
            'account_journal_id': journal.id,
            'picking_ids': [(6, 0, self.picking.ids)],
            'cost_lines': [(0, 0, {
                'name': 'Cost %s' % i,
                'product_id': self.service.id,
                'price_unit': amt,
                'split_method': 'by_quantity',
                'account_id': expense.id,
            }) for i, amt in enumerate(amounts)],
        })
        lc.compute_landed_cost()
        self.env.flush_all()  # SQL views read tables directly
        return lc

    def test_report_row_and_detail(self):
        lc = self._make_lc([50.0, 25.0])
        lc.button_validate()
        self.env.flush_all()
        rows = self.env['buz.landed.cost.report'].search([('landed_cost_id', '=', lc.id)])
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows.qty, 10)
        self.assertAlmostEqual(rows.base_cost, 1000.0)
        self.assertAlmostEqual(rows.landed_cost, 75.0)
        self.assertAlmostEqual(rows.total_cost, 1075.0)
        self.assertAlmostEqual(rows.unit_cost, 107.5)
        self.assertAlmostEqual(sum(rows.detail_ids.mapped('amount')), 75.0)
        self.assertEqual(len(rows.detail_ids), 2)
        # no FX applied: landed amount equals what the LC allocated
        self.assertAlmostEqual(rows.svl_landed_value, 75.0)
        self.assertAlmostEqual(rows.svl_landed_diff, 0.0)

    def test_draft_flagged_and_audit_clean(self):
        draft = self._make_lc([10.0])
        row = self.env['buz.landed.cost.report'].search([('landed_cost_id', '=', draft.id)])
        self.assertEqual(row.state, 'draft')
        draft.unlink()
        lc = self._make_lc([40.0])
        lc.button_validate()
        self.env.flush_all()
        audit = self.env['buz.landed.cost.audit'].search([('landed_cost_id', '=', lc.id)])
        self.assertAlmostEqual(audit.amount_total, 40.0)
        self.assertAlmostEqual(audit.alloc_total, 40.0)
        self.assertAlmostEqual(audit.svl_total, 40.0)
        self.assertFalse(audit.alloc_mismatch)
        self.assertFalse(audit.svl_over)

    def test_wizard_default_excludes_draft(self):
        wiz = self.env['buz.landed.cost.report.wizard'].create({})
        self.assertIn(('state', '=', 'done'), wiz._get_domain())

    def test_consumed_before_lc_is_not_a_defect(self):
        """Odoo capitalises LC only for stock on hand: 4 of 10 sold -> SVL = 60%."""
        wh = self.picking.picking_type_id.warehouse_id
        out = self.env['stock.picking'].create({
            'picking_type_id': wh.out_type_id.id,
            'location_id': wh.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [(0, 0, {
                'name': 'LC test out',
                'product_id': self.product.id,
                'product_uom_qty': 4,
                'product_uom': self.product.uom_id.id,
                'location_id': wh.lot_stock_id.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            })],
        })
        out.action_confirm()
        out.move_ids.quantity = 4
        out.move_ids.picked = True
        out._action_done()
        lc = self._make_lc([100.0])
        lc.button_validate()
        self.env.flush_all()
        row = self.env['buz.landed.cost.report'].search([('landed_cost_id', '=', lc.id)])
        self.assertAlmostEqual(row.landed_cost, 100.0)
        self.assertAlmostEqual(row.svl_landed_value, 60.0)
        self.assertAlmostEqual(row.svl_landed_diff, 40.0)
        audit = self.env['buz.landed.cost.audit'].search([('landed_cost_id', '=', lc.id)])
        self.assertAlmostEqual(audit.uncapitalised, 40.0)
        self.assertFalse(audit.svl_over)
        self.assertFalse(audit.alloc_mismatch)
