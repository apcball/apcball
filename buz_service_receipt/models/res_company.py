# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    service_receipt_attendee_employee_ids = fields.Many2many(
        'hr.employee',
        'res_company_service_receipt_employee_rel',
        'company_id',
        'employee_id',
        string='Service Receipt Calendar Employees',
        help='Employees who should be added automatically to service receipt calendar events.',
    )
    service_receipt_default_team_id = fields.Many2one(
        'service.team',
        string='Default Service Team',
        help='Default team assigned to new service receipts.',
    )
    service_receipt_return_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Return Picking Type',
        domain="[('code', '=', 'incoming')]",
        help='Operation type used when receiving returned products from customers (claim). '
             'Determines the document sequence number for return pickings.',
    )
    service_receipt_replacement_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Replacement Picking Type',
        domain="[('code', '=', 'outgoing')]",
        help='Operation type used when delivering replacement products to customers (claim). '
             'Determines the document sequence number for replacement deliveries.',
    )
