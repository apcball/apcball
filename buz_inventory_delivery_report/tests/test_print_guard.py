from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

REPORT = 'buz_inventory_delivery_report.delivery_report_tem_document'


@tagged('post_install', '-at_install')
class TestPrintGuard(TransactionCase):

    def _make_picking(self):
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'outgoing')], limit=1)
        return self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })

    def test_draft_blocked(self):
        picking = self._make_picking()
        self.assertEqual(picking.state, 'draft')
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_qweb_pdf(REPORT, picking.ids)

    def test_assigned_blocked(self):
        picking = self._make_picking()
        picking.state = 'assigned'
        with self.assertRaises(UserError) as ctx:
            self.env['ir.actions.report']._render_qweb_pdf(REPORT, picking.ids)
        self.assertIn(picking.name, str(ctx.exception))

    def test_borrow_equipment_blocked_unless_done(self):
        borrow = 'buz_inventory_delivery_report.borrow_equip_form_document'
        picking = self._make_picking()
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_qweb_pdf(borrow, picking.ids)
        picking.state = 'done'
        content, fmt = self.env['ir.actions.report']._render_qweb_pdf(borrow, picking.ids)
        self.assertTrue(content)

    def test_delivery_document_blocked_unless_done(self):
        report = 'buz_inventory_delivery_report.report_delivery_document'
        picking = self._make_picking()
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_qweb_pdf(report, picking.ids)
        picking.state = 'done'
        content, fmt = self.env['ir.actions.report']._render_qweb_pdf(report, picking.ids)
        self.assertTrue(content)

    def test_done_allowed(self):
        picking = self._make_picking()
        picking.state = 'done'
        content, fmt = self.env['ir.actions.report']._render_qweb_pdf(REPORT, picking.ids)
        self.assertTrue(content)
