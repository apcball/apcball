from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

REPORT = 'buz_delivery_report.report_picking_document_custom'


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

    def test_not_done_blocked(self):
        picking = self._make_picking()
        for state in ('draft', 'assigned'):
            picking.state = state
            with self.assertRaises(UserError) as ctx:
                self.env['ir.actions.report']._render_qweb_pdf(REPORT, picking.ids)
            self.assertIn(picking.name, str(ctx.exception))

    def test_receipt_blocked_unless_done(self):
        receipt = 'buz_delivery_report.report_picking_receipt_custom'
        picking = self._make_picking()
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_qweb_pdf(receipt, picking.ids)
        picking.state = 'done'
        content, fmt = self.env['ir.actions.report']._render_qweb_pdf(receipt, picking.ids)
        self.assertTrue(content)

    def test_done_allowed(self):
        picking = self._make_picking()
        picking.state = 'done'
        content, fmt = self.env['ir.actions.report']._render_qweb_pdf(REPORT, picking.ids)
        self.assertTrue(content)
