from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase


class TestShowLoan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Location = cls.env['stock.location']
        fg10 = Location.create({'name': 'FG10', 'usage': 'view'})
        fg40 = Location.create({'name': 'FG40', 'usage': 'view'})
        cls.source = Location.create({'name': 'Stock', 'usage': 'internal',
                                      'location_id': fg10.id})
        cls.return_dest = Location.create({'name': 'Stock', 'usage': 'internal',
                                           'location_id': fg40.id})
        cls.loan_dest = Location.create({'name': 'Showroom', 'usage': 'internal'})
        cls.partner = cls.env['res.partner'].create({'name': 'Show Borrower'})
        cls.product = cls.env['product.product'].create({'name': 'Show Product', 'type': 'product'})
        PickingType = cls.env['stock.picking.type']
        cls.bg_types = {}
        for code in ('BG-PJ', 'BG-RT', 'BG-OL'):
            sequence = cls.env['ir.sequence'].create({'name': code, 'code': code, 'prefix': code + '-'})
            cls.bg_types[code] = PickingType.create({
                'name': code, 'code': 'internal', 'sequence_code': code,
                'sequence_id': sequence.id, 'company_id': cls.env.company.id,
                'create_backorder': 'always',
                'default_location_src_id': cls.source.id,
                'default_location_dest_id': cls.loan_dest.id,
            })
        sequence = cls.env['ir.sequence'].create({'name': 'RBG', 'code': 'RBG', 'prefix': 'RBG/'})
        cls.rbg_type = PickingType.create({
            'name': 'RBG', 'code': 'internal', 'sequence_code': 'RBG',
            'sequence_id': sequence.id, 'company_id': cls.env.company.id,
            'default_location_src_id': cls.loan_dest.id,
            'default_location_dest_id': cls.return_dest.id,
        })

    def _loan(self, code='BG-PJ', qty=5, **values):
        vals = {
            'partner_id': self.partner.id,
            'picking_type_id': self.bg_types[code].id,
            'location_dest_id': self.loan_dest.id,
            'line_ids': [Command.create({
                'product_id': self.product.id,
                'uom_id': self.product.uom_id.id,
                'qty_requested': qty,
            })],
        }
        vals.update(values)
        return self.env['buz.show.loan'].create(vals)

    def _done(self, picking, qty):
        self.env['stock.quant']._update_available_quantity(self.product, picking.location_id, qty)
        picking.action_assign()
        picking.move_ids.write({'quantity': qty})
        picking.with_context(skip_immediate=True, skip_backorder=True).button_validate()
        self.assertEqual(picking.state, 'done')

    def _return(self, loan, qty):
        wizard = self.env['buz.show.loan.return.wizard'].with_context(
            default_loan_id=loan.id,
        ).create({'picking_type_id': self.rbg_type.id})
        wizard.line_ids.qty_return = qty
        action = wizard.action_confirm()
        return self.env['stock.picking'].browse(action['res_id'])

    def test_bg_types_and_confirm_once(self):
        for code in ('BG-PJ', 'BG-RT', 'BG-OL'):
            loan = self._loan(code)
            loan.action_confirm()
            self.assertEqual(loan.picking_id.location_id, self.source)
            self.assertEqual(loan.picking_id.location_dest_id, self.loan_dest)
            self.assertTrue(loan.name.startswith(code))
            self.assertEqual(loan.picking_id.show_loan_id, loan)
            with self.assertRaises(UserError):
                loan.action_confirm()
            with self.assertRaises(UserError):
                self.env['buz.show.loan.line'].create({
                    'loan_id': loan.id,
                    'product_id': self.product.id,
                    'uom_id': self.product.uom_id.id,
                    'qty_requested': 1,
                })

    def test_partial_returns_link_and_balance(self):
        loan = self._loan()
        loan.action_confirm()
        with self.assertRaises(UserError):
            loan.action_create_return()
        self._done(loan.picking_id, 5)
        first = self._return(loan, 2)
        self.assertEqual(first.origin, loan.picking_id.name)
        self.assertEqual(first.show_loan_id, loan)
        self.assertEqual(first.location_id, self.loan_dest)
        self.assertEqual(first.location_dest_id, self.return_dest)
        self.assertEqual(loan.line_ids.qty_available, 3)
        with self.assertRaises(ValidationError):
            self._return(loan, 4)
        self._done(first, 2)
        second = self._return(loan, 3)
        self._done(second, 3)
        self.assertEqual(loan.line_ids.qty_returned, 5)
        self.assertEqual(loan.line_ids.qty_available, 0)

    def test_cancelled_return_releases_balance(self):
        loan = self._loan()
        loan.action_confirm()
        self._done(loan.picking_id, 5)
        returned = self._return(loan, 3)
        self.assertEqual(loan.line_ids.qty_available, 2)
        returned.action_cancel()
        self.assertEqual(loan.line_ids.qty_available, 5)

    def test_validate_rejects_edited_over_return(self):
        loan = self._loan()
        loan.action_confirm()
        self._done(loan.picking_id, 5)
        returned = self._return(loan, 2)
        self.env['stock.quant']._update_available_quantity(self.product, self.loan_dest, 6)
        returned.action_assign()
        returned.move_ids.write({'quantity': 6})
        with self.assertRaises(ValidationError):
            returned.with_context(skip_immediate=True, skip_backorder=True).button_validate()

    def test_bg_backorder_keeps_loan_link(self):
        loan = self._loan()
        loan.action_confirm()
        self.env['stock.quant']._update_available_quantity(self.product, self.source, 5)
        picking = loan.picking_id
        picking.action_assign()
        picking.move_ids.write({'quantity': 2})
        picking.with_context(skip_immediate=True).button_validate()
        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertEqual(len(backorder), 1)
        self.assertEqual(backorder.show_loan_id, loan)
        self.assertEqual(backorder.show_loan_role, 'loan')
        self.assertEqual(backorder.move_ids.show_loan_line_id, loan.line_ids)
        self.assertEqual(loan.line_ids.qty_issued, 2)
        self._done(backorder, 3)
        self.assertEqual(loan.line_ids.qty_issued, 5)

    def test_menu_follows_transfers(self):
        menu = self.env.ref('buz_show_loan.menu_show_loan')
        self.assertEqual(menu.parent_id, self.env.ref('stock.menu_stock_warehouse_mgmt'))
        self.assertEqual(menu.sequence, 2)
        self.assertEqual(self.env.ref('stock.menu_stock_adjustments').sequence, 3)

    def test_transfer_header_fields(self):
        tag = self.env['buz.picking.tag'].create({'name': 'Show loan'})
        scheduled = fields.Datetime.to_datetime('2026-11-26 08:30:00')
        loan = self._loan(
            requisition_order='REQ-001', scheduled_date=scheduled,
            origin='REQUEST-001', tag_ids=[Command.set(tag.ids)],
            analytic_auto_sync=False,
        )
        self.assertEqual(loan.location_id, self.source)
        loan.action_confirm()
        picking = loan.picking_id
        self.assertEqual(picking.partner_id, loan.partner_id)
        self.assertEqual(picking.picking_type_id, loan.picking_type_id)
        self.assertEqual(picking.scheduled_date, scheduled)
        self.assertEqual(picking.origin, 'REQUEST-001')
        self.assertEqual(picking.tag_ids, tag)
        if 'requisition_order' in picking._fields:
            self.assertEqual(picking.requisition_order, 'REQ-001')
        if 'analytic_auto_sync' in picking._fields:
            self.assertFalse(picking.analytic_auto_sync)
