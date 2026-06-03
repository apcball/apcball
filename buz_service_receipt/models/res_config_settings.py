# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    service_receipt_attendee_employee_ids = fields.Many2many(
        'hr.employee',
        related='company_id.service_receipt_attendee_employee_ids',
        string='Service Receipt Calendar Employees',
        readonly=False,
        help='Employees who should receive service receipt calendar appointments automatically.',
    )
    service_receipt_default_team_id = fields.Many2one(
        'service.team',
        related='company_id.service_receipt_default_team_id',
        string='Default Service Team',
        readonly=False,
        help='Default team assigned to new service receipts.',
    )
    service_receipt_return_picking_type_id = fields.Many2one(
        'stock.picking.type',
        related='company_id.service_receipt_return_picking_type_id',
        string='Return Picking Type',
        readonly=False,
        domain="[('code', '=', 'incoming')]",
        help='Operation type for receiving returned products from customers. '
             'Controls the document sequence number used.',
    )
    service_receipt_replacement_picking_type_id = fields.Many2one(
        'stock.picking.type',
        related='company_id.service_receipt_replacement_picking_type_id',
        string='Replacement Picking Type',
        readonly=False,
        domain="[('code', '=', 'outgoing')]",
        help='Operation type for delivering replacement products to customers. '
             'Controls the document sequence number used.',
    )
