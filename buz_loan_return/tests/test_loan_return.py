# -*- coding: utf-8 -*-

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestShowLoanReturn(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        cls.source_location = cls.warehouse.lot_stock_id
        cls.show_location = cls.env['stock.location'].create({
            'name': 'Show Loan Test Location',
            'usage': 'internal',
            'location_id': cls.source_location.id,
            'company_id': cls.company.id,
        })
        cls.return_location = cls.env['stock.location'].create({
            'name': 'Show Return Test Location',
            'usage': 'internal',
            'location_id': cls.source_location.id,
            'company_id': cls.company.id,
        })
        cls.loan_type = cls._create_picking_type(
            'BG-RT', 'Test Show Loan RT', cls.source_location, cls.show_location,
        )
        cls.loan_type_pj = cls._create_picking_type(
            'BG-PJ', 'Test Show Loan PJ', cls.source_location, cls.show_location,
        )
        cls.loan_type_ol = cls._create_picking_type(
            'BG-OL', 'Test Show Loan OL', cls.source_location, cls.show_location,
        )
        cls.loan_type_ambiguous = cls._create_picking_type(
            'BG-RT-BG-PJ', 'Test Ambiguous Show Loan', cls.source_location, cls.show_location,
        )
        cls.loan_type_missing = cls._create_picking_type(
            'LOAN', 'Test Unmarked Loan', cls.source_location, cls.show_location,
        )
        cls.return_type = cls._create_picking_type(
            'RBG', 'Test Show Return', cls.show_location, cls.return_location,
        )
        cls.partner = cls.env['res.partner'].create({'name': 'Show Loan Test Partner'})
        cls.product = cls.env['product.product'].create({
            'name': 'Show Loan Test Product',
            'type': 'product',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'uom_po_id': cls.env.ref('uom.product_uom_unit').id,
        })
        cls.env['stock.quant']._update_available_quantity(
            cls.product, cls.source_location, 20.0,
        )

    @classmethod
    def _create_picking_type(cls, sequence_code, name, source, destination):
        return cls.env['stock.picking.type'].create({
            'name': name,
            'code': 'internal',
            'sequence_code': sequence_code,
            'warehouse_id': cls.warehouse.id,
            'default_location_src_id': source.id,
            'default_location_dest_id': destination.id,
            'company_id': cls.company.id,
        })

    def _create_completed_loan(self, quantity=5.0):
        wizard = self.env['buz.loan.return.loan.wizard'].create({
            'company_id': self.company.id,
            'operation_type_id': self.loan_type.id,
            'partner_id': self.partner.id,
            'location_id': self.source_location.id,
            'location_dest_id': self.show_location.id,
            'line_ids': [Command.create({
                'product_id': self.product.id,
                'quantity': quantity,
            })],
        })
        action = wizard.action_create_loan()
        picking = self.env['stock.picking'].browse(action['res_id'])
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.write({'quantity': quantity})
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        return picking

    def _create_return(self, loan, quantity):
        wizard = self.env['buz.loan.return.return.wizard'].create({
            'source_picking_id': loan.id,
            'operation_type_id': self.return_type.id,
            'scheduled_date': loan.scheduled_date,
            'location_id': loan.location_dest_id.id,
            'location_dest_id': self.return_location.id,
            'line_ids': [Command.create({
                'product_id': self.product.id,
                'delivered_qty': 5.0,
                'reserved_qty': 0.0,
                'remaining_qty': quantity,
                'quantity': quantity,
            })],
        })
        action = wizard.action_create_return()
        return self.env['stock.picking'].browse(action['res_id'])

    def test_operation_type_determines_rt_pj_ol_and_rejects_missing_or_ambiguous_markers(self):
        wizard_model = self.env['buz.loan.return.loan.wizard']
        self.assertEqual(wizard_model._loan_type_from_operation_type(self.loan_type), 'rt')
        self.assertEqual(wizard_model._loan_type_from_operation_type(self.loan_type_pj), 'pj')
        self.assertEqual(wizard_model._loan_type_from_operation_type(self.loan_type_ol), 'ol')
        with self.assertRaises(ValidationError):
            wizard_model._loan_type_from_operation_type(self.loan_type_missing)
        with self.assertRaises(ValidationError):
            wizard_model._loan_type_from_operation_type(self.loan_type_ambiguous)

    def test_wizard_copies_source_document_and_tags_to_loan(self):
        tag = self.env['buz.picking.tag'].create({'name': 'Loan wizard test tag'})
        wizard = self.env['buz.loan.return.loan.wizard'].create({
            'company_id': self.company.id,
            'operation_type_id': self.loan_type.id,
            'partner_id': self.partner.id,
            'location_id': self.source_location.id,
            'location_dest_id': self.show_location.id,
            'origin': 'External reference 123',
            'tag_ids': [Command.set(tag.ids)],
            'line_ids': [Command.create({
                'product_id': self.product.id,
                'quantity': 1.0,
            })],
        })
        action = wizard.action_create_loan()
        picking = self.env['stock.picking'].browse(action['res_id'])
        self.assertEqual(picking.loan_return_type, 'rt')
        self.assertEqual(picking.origin, 'External reference 123')
        self.assertEqual(picking.tag_ids, tag)

    def test_single_loan_can_have_multiple_returns_and_cancel_releases_balance(self):
        loan = self._create_completed_loan(5.0)
        first_return = self._create_return(loan, 2.0)
        second_return = self._create_return(loan, 3.0)

        self.assertEqual(first_return.loan_return_source_id, loan)
        self.assertEqual(second_return.loan_return_source_id, loan)
        self.assertAlmostEqual(
            loan._get_loan_return_balances()[self.product.id]['remaining'], 0.0,
        )

        first_return.action_cancel()
        self.assertAlmostEqual(
            loan._get_loan_return_balances()[self.product.id]['remaining'], 2.0,
        )

    def test_return_documents_cannot_reserve_more_than_done_loan_quantity(self):
        loan = self._create_completed_loan(5.0)
        self._create_return(loan, 3.0)

        with self.assertRaises(ValidationError):
            self._create_return(loan, 3.0)

    def test_partial_return_keeps_the_backorder_linked_and_reserved(self):
        loan = self._create_completed_loan(5.0)
        picking = self._create_return(loan, 5.0)
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.write({'quantity': 3.0})

        action = picking.button_validate()
        self.assertEqual(action.get('res_model'), 'stock.backorder.confirmation')
        wizard = self.env[action['res_model']].with_context(**action['context']).create({
            'pick_ids': [Command.set(picking.ids)],
            'show_transfers': False,
        })
        wizard.process()

        self.assertEqual(picking.state, 'done')
        backorder = picking.backorder_ids
        self.assertEqual(len(backorder), 1)
        self.assertEqual(backorder.loan_return_role, 'return')
        self.assertEqual(backorder.loan_return_source_id, loan)
        self.assertAlmostEqual(backorder.move_ids.product_uom_qty, 2.0)
        self.assertAlmostEqual(
            loan._get_loan_return_balances()[self.product.id]['reserved'], 5.0,
        )
        backorder.action_cancel()
        self.assertAlmostEqual(
            loan._get_loan_return_balances()[self.product.id]['remaining'], 2.0,
        )

    def test_return_must_reference_a_tracked_completed_loan(self):
        untracked = self.env['stock.picking'].create({
            'picking_type_id': self.loan_type.id,
            'location_id': self.source_location.id,
            'location_dest_id': self.show_location.id,
        })
        with self.assertRaises(ValidationError):
            self.env['stock.picking'].create({
                'loan_return_role': 'return',
                'loan_return_source_id': untracked.id,
                'picking_type_id': self.return_type.id,
                'location_id': self.show_location.id,
                'location_dest_id': self.return_location.id,
            })
