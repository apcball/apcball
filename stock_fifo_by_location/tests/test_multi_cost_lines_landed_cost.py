# -*- coding: utf-8 -*-
"""
Tests for: Multiple cost lines on Landed Cost → warehouse distribution must sum correctly.

Bug: When a Landed Cost document has multiple cost lines (e.g., Duty 200 + Tax 100),
the warehouse distribution records (stock.valuation.layer.landed.cost) only stored
the LAST cost line's allocation, overwriting previous ones.

Root cause: _allocate_landed_cost_to_current_positions searched for existing records
by (valuation_layer_id, warehouse_id, landed_cost_id) without cost_line granularity.
The second cost line found the existing record from the first cost line and OVERWROTE it
instead of ADDING to it.

Fix: When existing record is found, ADD the new allocated_value to existing.landed_cost_value.
"""

from odoo.tests.common import TransactionCase, tagged


def _get_stock_account_properties(env):
    """Return or create the stock journal + stock input/output accounts for real_time tests."""
    journal = env['account.journal'].search([
        ('company_id', '=', env.company.id),
        ('type', '=', 'general'),
    ], limit=1)
    if not journal:
        journal = env['account.journal'].create({
            'name': 'Stock Journal',
            'code': 'STK',
            'type': 'general',
            'company_id': env.company.id,
        })

    account_model = env['account.account']

    stock_input = account_model.search([
        ('company_id', '=', env.company.id),
        ('code', '=', 'stock.input.mc'),
    ], limit=1)
    if not stock_input:
        stock_input = account_model.create({
            'name': 'Stock Input MC Test',
            'code': 'stock.input.mc',
            'account_type': 'liability_current',
            'company_id': env.company.id,
        })

    stock_output = account_model.search([
        ('company_id', '=', env.company.id),
        ('code', '=', 'stock.output.mc'),
    ], limit=1)
    if not stock_output:
        stock_output = account_model.create({
            'name': 'Stock Output MC Test',
            'code': 'stock.output.mc',
            'account_type': 'asset_current',
            'company_id': env.company.id,
        })

    stock_valuation = account_model.search([
        ('company_id', '=', env.company.id),
        ('code', '=', 'stock.val.mc'),
    ], limit=1)
    if not stock_valuation:
        stock_valuation = account_model.create({
            'name': 'Stock Valuation MC Test',
            'code': 'stock.val.mc',
            'account_type': 'asset_current',
            'company_id': env.company.id,
        })

    expense = account_model.search([
        ('company_id', '=', env.company.id),
        ('code', '=', 'stock.exp.mc'),
    ], limit=1)
    if not expense:
        expense = account_model.create({
            'name': 'Stock Expense MC Test',
            'code': 'stock.exp.mc',
            'account_type': 'expense',
            'company_id': env.company.id,
        })

    return {
        'journal': journal,
        'stock_input': stock_input,
        'stock_output': stock_output,
        'stock_valuation': stock_valuation,
        'expense': expense,
    }


@tagged('post_install', '-at_install')
class TestMultiCostLinesWarehouseDistribution(TransactionCase):
    """
    Test that when a Landed Cost has multiple cost lines,
    the per-warehouse landed_cost_value SUMS all cost lines correctly.
    """

    def setUp(self):
        super().setUp()
        self.landed_cost_model = self.env['stock.landed.cost']
        self.landed_cost_line_model = self.env['stock.landed.cost.lines']
        self.lc_location_model = self.env['stock.valuation.layer.landed.cost']
        self.company = self.env.company

        accounts = _get_stock_account_properties(self.env)

        self.product_category = self.env['product.category'].create({
            'name': 'Test Multi Cost Lines',
            'property_cost_method': 'fifo',
            'property_valuation': 'real_time',
            'property_stock_account_input_categ_id': accounts['stock_input'].id,
            'property_stock_account_output_categ_id': accounts['stock_output'].id,
            'property_stock_valuation_account_id': accounts['stock_valuation'].id,
            'property_stock_journal': accounts['journal'].id,
        })

        self.product = self.env['product.product'].create({
            'name': 'Test Multi LC Product',
            'type': 'product',
            'categ_id': self.product_category.id,
            'standard_price': 100.0,
        })

        expense_account = accounts['expense']

        self.cost_product_1 = self.env['product.product'].create({
            'name': 'Test Duty',
            'type': 'service',
            'landed_cost_ok': True,
            'categ_id': self.product_category.id,
            'property_account_expense_id': expense_account.id,
        })
        self.cost_product_2 = self.env['product.product'].create({
            'name': 'Test Import Tax',
            'type': 'service',
            'landed_cost_ok': True,
            'categ_id': self.product_category.id,
            'property_account_expense_id': expense_account.id,
        })
        self.cost_product_3 = self.env['product.product'].create({
            'name': 'Test Freight',
            'type': 'service',
            'landed_cost_ok': True,
            'categ_id': self.product_category.id,
            'property_account_expense_id': expense_account.id,
        })

        self.warehouse_1 = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company.id)], limit=1
        )
        self.warehouse_2 = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company.id),
            ('id', '!=', self.warehouse_1.id),
        ], limit=1)
        if not self.warehouse_2:
            self.warehouse_2 = self.env['stock.warehouse'].create({
                'name': 'MC Test WH2',
                'code': 'MCW2',
                'company_id': self.company.id,
            })

        self.supplier_location = self.env.ref('stock.stock_location_suppliers')
        self.customer_location = self.env.ref('stock.stock_location_customers')

        self.account_journal = self.env['account.journal'].search([
            ('company_id', '=', self.company.id),
            ('type', '=', 'general'),
        ], limit=1)

    # ── Helpers ──

    def _validate_picking(self, picking):
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_line_ids:
            ml.quantity = ml.move_id.product_uom_qty
        picking.button_validate()

    def _create_receipt(self, warehouse, qty, unit_cost):
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.in_type_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': f'Receipt {warehouse.name}',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
            'price_unit': unit_cost,
        })
        self._validate_picking(picking)
        return picking

    def _create_transfer(self, source_wh, dest_wh, qty):
        picking = self.env['stock.picking'].create({
            'picking_type_id': source_wh.int_type_id.id,
            'location_id': source_wh.lot_stock_id.id,
            'location_dest_id': dest_wh.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': f'Transfer {source_wh.name}->{dest_wh.name}',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': source_wh.lot_stock_id.id,
            'location_dest_id': dest_wh.lot_stock_id.id,
        })
        self._validate_picking(picking)
        return picking

    def _validate_landed_cost(self, receipt_picking, cost_lines_data):
        """
        Create and validate a landed cost on the given receipt.

        cost_lines_data: list of (name, product, amount, split_method)
        """
        landed_cost = self.landed_cost_model.create({
            'target_model': 'picking',
            'picking_ids': [(6, 0, [receipt_picking.id])],
        })
        for name, product, amount, split_method in cost_lines_data:
            self.landed_cost_line_model.create({
                'name': name,
                'product_id': product.id,
                'split_method': split_method,
                'price_unit': amount,
                'cost_id': landed_cost.id,
            })

        landed_cost.compute_landed_cost()
        landed_cost.account_journal_id = self.account_journal
        landed_cost.button_validate()
        return landed_cost

    def _get_wh_lc_total(self, landed_cost, warehouse):
        """Get total landed_cost_value for a specific warehouse under a LC."""
        records = self.lc_location_model.search([
            ('landed_cost_id', '=', landed_cost.id),
            ('warehouse_id', '=', warehouse.id),
        ])
        return sum(records.mapped('landed_cost_value'))

    # ═══════════════════════════════════════════
    # Tests
    # ═══════════════════════════════════════════

    def test_01_two_cost_lines_single_warehouse(self):
        """
        LC with 2 cost lines (Duty 200 + Tax 100), stock at 1 warehouse.
        Total warehouse distribution must be 300, NOT just the last cost line (100).
        """
        receipt = self._create_receipt(self.warehouse_1, 10, 500)

        landed_cost = self._validate_landed_cost(receipt, [
            ('Duty', self.cost_product_1, 200.0, 'by_quantity'),
            ('Import Tax', self.cost_product_2, 100.0, 'by_quantity'),
        ])

        total_lc = sum(
            self.lc_location_model.search([
                ('landed_cost_id', '=', landed_cost.id),
            ]).mapped('landed_cost_value')
        )
        self.assertAlmostEqual(total_lc, 300.0, places=2,
                               msg="Total warehouse LC must equal sum of all cost lines (200+100=300)")

    def test_02_two_cost_lines_split_warehouses(self):
        """
        LC with 2 cost lines (Duty 200 + Tax 100), stock split across 2 warehouses.
        WH1: 5 units, WH2: 5 units → each gets 50% of total = 150 each.
        """
        receipt = self._create_receipt(self.warehouse_1, 10, 500)
        self._create_transfer(self.warehouse_1, self.warehouse_2, 5)

        landed_cost = self._validate_landed_cost(receipt, [
            ('Duty', self.cost_product_1, 200.0, 'by_quantity'),
            ('Import Tax', self.cost_product_2, 100.0, 'by_quantity'),
        ])

        wh1_total = self._get_wh_lc_total(landed_cost, self.warehouse_1)
        wh2_total = self._get_wh_lc_total(landed_cost, self.warehouse_2)

        self.assertAlmostEqual(wh1_total, 150.0, places=2,
                               msg="WH1 (5/10 = 50%) gets 50% of 300 = 150")
        self.assertAlmostEqual(wh2_total, 150.0, places=2,
                               msg="WH2 (5/10 = 50%) gets 50% of 300 = 150")
        self.assertAlmostEqual(wh1_total + wh2_total, 300.0, places=2,
                               msg="Total across all warehouses = total LC amount")

    def test_03_three_cost_lines_split_warehouses(self):
        """
        LC with 3 cost lines (Duty 200 + Tax 100 + Freight 300), stock split 60/40.
        WH1: 6 units (60%), WH2: 4 units (40%).
        Total = 600. Expected: WH1=360, WH2=240.
        """
        receipt = self._create_receipt(self.warehouse_1, 10, 500)
        self._create_transfer(self.warehouse_1, self.warehouse_2, 4)

        landed_cost = self._validate_landed_cost(receipt, [
            ('Duty', self.cost_product_1, 200.0, 'by_quantity'),
            ('Import Tax', self.cost_product_2, 100.0, 'by_quantity'),
            ('Freight', self.cost_product_3, 300.0, 'by_quantity'),
        ])

        wh1_total = self._get_wh_lc_total(landed_cost, self.warehouse_1)
        wh2_total = self._get_wh_lc_total(landed_cost, self.warehouse_2)

        self.assertAlmostEqual(wh1_total, 360.0, places=2,
                               msg="WH1 (6/10) gets 60% of 600 = 360")
        self.assertAlmostEqual(wh2_total, 240.0, places=2,
                               msg="WH2 (4/10) gets 40% of 600 = 240")

    def test_04_two_cost_lines_different_split_methods(self):
        """
        LC with 2 cost lines using different split methods.
        Duty 200 (by_quantity) + Freight 100 (equal).
        Stock at 1 warehouse — both should sum to 300.
        """
        receipt = self._create_receipt(self.warehouse_1, 10, 500)

        landed_cost = self._validate_landed_cost(receipt, [
            ('Duty', self.cost_product_1, 200.0, 'by_quantity'),
            ('Freight', self.cost_product_3, 100.0, 'equal'),
        ])

        total_lc = sum(
            self.lc_location_model.search([
                ('landed_cost_id', '=', landed_cost.id),
            ]).mapped('landed_cost_value')
        )
        self.assertAlmostEqual(total_lc, 300.0, places=2,
                               msg="Different split methods, total must still be 300")

    def test_05_report_warehouse_distribution_matches_lc_total(self):
        """
        End-to-end: validate LC with 2 cost lines, export report,
        verify Warehouse Distribution section totals match LC amount_total.
        """
        receipt = self._create_receipt(self.warehouse_1, 10, 1500)
        self._create_transfer(self.warehouse_1, self.warehouse_2, 5)

        landed_cost = self._validate_landed_cost(receipt, [
            ('Duty', self.cost_product_1, 200.0, 'by_quantity'),
            ('Import Tax', self.cost_product_2, 100.0, 'by_quantity'),
        ])

        # Verify via the same query the report uses
        lc_records = self.lc_location_model.search([
            ('landed_cost_id', '=', landed_cost.id),
        ])

        wh_total = sum(lc_records.mapped('landed_cost_value'))
        self.assertAlmostEqual(wh_total, 300.0, places=2,
                               msg="Report warehouse total must equal LC total (300)")
