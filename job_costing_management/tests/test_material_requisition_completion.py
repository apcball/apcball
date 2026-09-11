# -*- coding: utf-8 -*-

from datetime import date

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestMaterialRequisitionCompletion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.project = cls.env['project.project'].create({
            'name': 'Material Requisition Completion Test',
            'company_id': cls.company.id,
        })
        product_template = cls.env['product.template'].create({
            'name': 'Completion Test Material',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'uom_po_id': cls.env.ref('uom.product_uom_unit').id,
        })
        cls.product = product_template.product_variant_id
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Completion Test Vendor',
            'supplier_rank': 1,
        })

    def _create_requisition(self, actions):
        return self.env['material.requisition'].create({
            'project_id': self.project.id,
            'company_id': self.company.id,
            'required_date': date.today(),
            'state': 'ordered',
            'line_ids': [fields.Command.create({
                'product_id': self.product.id,
                'description': 'Completion test line',
                'quantity': quantity,
                'uom_id': self.product.uom_id.id,
                'requisition_action': action,
                'vendor_id': self.vendor.id if action == 'purchase' else False,
            }) for action, quantity in actions],
        })

    def _create_purchase_order(self, requisition_line, quantity):
        return self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'material_requisition_id': requisition_line.requisition_id.id,
            'order_line': [fields.Command.create({
                'product_id': self.product.id,
                'name': self.product.name,
                'product_qty': quantity,
                'product_uom': self.product.uom_id.id,
                'price_unit': 1.0,
                'material_requisition_line_id': requisition_line.id,
            })],
        })

    def test_purchase_requisition_waits_for_full_ordered_quantity(self):
        requisition = self._create_requisition([('purchase', 5.0)])
        line = requisition.line_ids
        purchase_order = self._create_purchase_order(line, 4.0)
        purchase_order.write({'state': 'purchase'})

        requisition._check_and_mark_done()
        self.assertEqual(requisition.state, 'ordered')

        purchase_order.order_line.write({'product_qty': 5.0})
        requisition._check_and_mark_done()
        self.assertEqual(requisition.state, 'received')

    def test_completed_internal_transfer_marks_requisition_done(self):
        requisition = self._create_requisition([('internal', 2.0)])
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_internal').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            'origin': requisition.name,
        })
        requisition.line_ids.write({
            'picking_ids': [fields.Command.link(picking.id)],
        })

        requisition._check_and_mark_done()
        self.assertEqual(requisition.state, 'ordered')

        picking.write({'state': 'done'})
        requisition._check_and_mark_done()
        self.assertEqual(requisition.state, 'received')

    def test_create_rfq_requires_selection(self):
        requisition = self._create_requisition([('purchase', 5.0)])
        requisition.state = 'approved'
        with self.assertRaises(ValidationError):
            requisition.action_create_purchase_order()

    def test_create_rfq_only_selected_lines_and_remaining_qty(self):
        requisition = self._create_requisition([
            ('purchase', 5.0),
            ('purchase', 3.0),
        ])
        requisition.state = 'approved'
        line_a, line_b = requisition.line_ids

        # Partially cover line_a with an existing (non-cancelled) PO first.
        self._create_purchase_order(line_a, 2.0)

        line_a.select_for_rfq = True
        requisition.action_create_purchase_order()

        self.assertFalse(line_a.select_for_rfq, 'checkbox should reset after RFQ creation')
        self.assertFalse(line_b.select_for_rfq)
        self.assertEqual(requisition.state, 'ordered')

        po_lines_a = self.env['purchase.order.line'].search([
            ('material_requisition_line_id', '=', line_a.id),
        ])
        # 2.0 already on the earlier PO + 3.0 remaining now placed = 5.0 total.
        self.assertEqual(sum(po_lines_a.mapped('product_qty')), 5.0)

        po_lines_b = self.env['purchase.order.line'].search([
            ('material_requisition_line_id', '=', line_b.id),
        ])
        self.assertFalse(po_lines_b, 'unselected line should not get a PO')

        # Second round: select line_b while requisition is already 'ordered'.
        line_b.select_for_rfq = True
        requisition.action_create_purchase_order()

        po_lines_b = self.env['purchase.order.line'].search([
            ('material_requisition_line_id', '=', line_b.id),
        ])
        self.assertEqual(sum(po_lines_b.mapped('product_qty')), 3.0)
        self.assertFalse(line_b.select_for_rfq)

    def test_mixed_requisition_requires_purchase_and_transfer_completion(self):
        requisition = self._create_requisition([
            ('purchase', 3.0),
            ('internal', 1.0),
        ])
        purchase_line, internal_line = requisition.line_ids
        purchase_order = self._create_purchase_order(purchase_line, 3.0)
        purchase_order.write({'state': 'purchase'})
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_internal').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            'origin': requisition.name,
        })
        internal_line.write({
            'picking_ids': [fields.Command.link(picking.id)],
        })

        requisition._check_and_mark_done()
        self.assertEqual(requisition.state, 'ordered')

        picking.write({'state': 'done'})
        requisition._check_and_mark_done()
        self.assertEqual(requisition.state, 'received')
