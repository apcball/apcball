# pylint: disable=protected-access  # tests exercise internal entry points
from datetime import datetime, timedelta

from odoo import Command
from odoo.tests.common import tagged

from odoo.addons.buz_production_planning.engine.mrp_netting import PlanGatherer

from .common import MONDAY, PlanCommon


@tagged('post_install', '-at_install')
class TestComputeIntegration(PlanCommon):
    """End to end through the database (own warehouse and product)."""

    def setUp(self):
        super().setUp()
        self.wh = self.env['stock.warehouse'].create({'name': 'TEST PLAN WH', 'code': 'TPW'})
        self.prod = self._product('INT')
        self.env['stock.quant']._update_available_quantity(self.prod, self.wh.lot_stock_id, 10)
        customers = self.env.ref('stock.stock_location_customers')
        move_date = datetime.combine(MONDAY + timedelta(days=9), datetime.min.time())
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.wh.out_type_id.id,
            'location_id': self.wh.lot_stock_id.id,
            'location_dest_id': customers.id,
            'scheduled_date': move_date,
            'move_ids': [Command.create({
                'name': 'plan test', 'product_id': self.prod.id, 'product_uom_qty': 30,
                'location_id': self.wh.lot_stock_id.id, 'location_dest_id': customers.id,
                'date': move_date})],
        })
        picking.action_confirm()
        self.run_ = self.env['buz.plan.run'].create({
            'date_from': MONDAY, 'horizon_weeks': 3, 'warehouse_ids': [Command.set(self.wh.ids)]})

    def _mine(self):
        return self.run_.suggestion_ids.filtered(lambda s: s.product_id == self.prod)

    def test_compute_creates_suggestion(self):
        self.run_.action_compute()
        self.assertEqual(self.run_.state, 'computed')
        sugg = self._mine()
        self.assertEqual(len(sugg), 1)
        self.assertEqual((sugg.action, sugg.qty, sugg.onhand_qty), ('buy', 20, 10))
        self.assertEqual(sugg.date_need, MONDAY + timedelta(days=7))
        demand = self.run_.demand_line_ids.filtered(lambda d: d.product_id == self.prod)
        self.assertEqual(sum(demand.filtered(lambda d: d.source == 'delivery').mapped('qty')), 30)

    def test_recompute_keeps_approved_and_deducts_it(self):
        self.run_.action_compute()
        self._mine().action_approve()
        self.run_.action_compute()
        sugg = self._mine()
        self.assertEqual(len(sugg), 1, "approved kept, no duplicate proposal")
        self.assertEqual(sugg.state, 'approved')

    def test_recompute_replaces_proposed(self):
        self.run_.action_compute()
        first = self._mine()
        self.run_.action_compute()
        self.assertEqual(len(self._mine()), 1)
        self.assertFalse(first.exists())

    def test_recompute_after_documents_created(self):
        """Creating part of the documents must not freeze the plan."""
        self.run_.action_compute()
        self.run_.state = 'confirmed'
        self.run_.action_compute()
        self.assertEqual(self.run_.state, 'computed')

    def _done_out_move(self, product, dest, qty, day):
        move = self.env['stock.move'].create({
            'name': 'history', 'product_id': product.id, 'product_uom_qty': qty,
            'product_uom': product.uom_id.id, 'picking_type_id': self.wh.out_type_id.id,
            'location_id': self.wh.lot_stock_id.id, 'location_dest_id': dest.id})
        # History only: the planner reads state/date/qty, so no stock operation is needed.
        move.write({'state': 'done', 'date': day})
        return move

    def test_forecast_ignores_vendor_returns_and_adjustments(self):
        cutoff = datetime(2026, 4, 1).date()
        returned = self._product('RETURNED')
        sold = self._product('SOLD')
        day = datetime(2026, 11, 2, 3, 0)
        self._done_out_move(returned, self.env.ref('stock.stock_location_suppliers'), 120, day)
        self._done_out_move(
            returned, self.env['stock.location'].search([('usage', '=', 'inventory')], limit=1), 60, day)
        self._done_out_move(sold, self.env.ref('stock.stock_location_customers'), 120, day)
        self.env.flush_all()  # _forecast is raw SQL; gather() normally flushes first
        forecast = PlanGatherer(self.run_)._forecast(MONDAY, 12, cutoff)
        self.assertNotIn(returned.id, forecast, "a return to the vendor is not a sale")
        self.assertAlmostEqual(forecast[sold.id], 10.0)

    def test_make_takes_production_line_of_latest_mo(self):
        made = self._product('MADE')
        comp = self._product('MADE-COMP')
        self._bom(made, [(comp, 1)])
        self.env['mrp.production'].create({
            'product_id': made.id, 'product_qty': 1, 'picking_type_id': self.wh.manu_type_id.id})
        self.env['buz.plan.product.param'].create({'product_id': made.id, 'safety_stock': 5})
        self.run_.action_compute()
        sugg = self.run_.suggestion_ids.filtered(lambda s: s.product_id == made)
        self.assertEqual((sugg.action, sugg.picking_type_id), ('make', self.wh.manu_type_id))

    def test_draft_mo_of_another_plan_counts_as_supply(self):
        """A second plan must not propose again what the first plan already drafted."""
        other = self.env['buz.plan.run'].create({
            'date_from': MONDAY, 'horizon_weeks': 3, 'warehouse_ids': [Command.set(self.wh.ids)],
            'state': 'confirmed'})
        mo = self.env['mrp.production'].create({
            'product_id': self.prod.id, 'product_qty': 20, 'picking_type_id': self.wh.manu_type_id.id})
        self.assertEqual(mo.state, 'draft')
        self.env['buz.plan.suggestion'].create({
            'run_id': other.id, 'product_id': self.prod.id, 'action': 'make', 'qty': 20,
            'uom_id': self.prod.uom_id.id, 'date_need': MONDAY + timedelta(days=7),
            'date_release': MONDAY, 'state': 'done', 'production_id': mo.id})
        self.run_.action_compute()
        self.assertFalse(self._mine(), "20 short, 20 already drafted by the other plan")
        mo.action_cancel()
        self.run_.action_compute()
        self.assertEqual(self._mine().qty, 20, "a cancelled draft is no supply")

    def test_draft_mo_of_another_plan_still_needs_its_components(self):
        """Plan A drafted the FG MO but no RM document: plan B must still buy the RM."""
        made = self._product('DRAFTED')
        comp = self._product('DRAFTED-COMP')
        bom = self._bom(made, [(comp, 3)])
        other = self.env['buz.plan.run'].create({
            'date_from': MONDAY, 'horizon_weeks': 3, 'warehouse_ids': [Command.set(self.wh.ids)],
            'state': 'confirmed'})
        mo = self.env['mrp.production'].create({
            'product_id': made.id, 'product_qty': 4, 'bom_id': bom.id,
            'picking_type_id': self.wh.manu_type_id.id})
        self.env['buz.plan.suggestion'].create({
            'run_id': other.id, 'product_id': made.id, 'action': 'make', 'qty': 4,
            'uom_id': made.uom_id.id, 'bom_id': bom.id, 'date_need': MONDAY + timedelta(days=7),
            'date_release': MONDAY + timedelta(days=4), 'state': 'done', 'production_id': mo.id})
        self.run_.action_compute()
        sugg = self.run_.suggestion_ids
        self.assertFalse(sugg.filtered(lambda s: s.product_id == made), "FG covered by the draft")
        rm = sugg.filtered(lambda s: s.product_id == comp)
        self.assertEqual((rm.action, rm.qty), ('buy', 12))
