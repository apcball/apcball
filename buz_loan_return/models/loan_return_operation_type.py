# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class LoanReturnOperationType(models.Model):
    _name = 'buz.loan.return.operation.type'
    _description = 'BG/RBG Operation Type Configuration'
    _order = 'company_id, document_kind, picking_type_id'
    _rec_name = 'picking_type_id'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    document_kind = fields.Selection(
        [
            ('loan', 'BG / Loan'),
            ('return', 'RBG / Return'),
        ],
        string='Document Type',
        required=True,
        default='loan',
    )
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        required=True,
        domain=[('code', '=', 'internal')],
        ondelete='restrict',
    )

    _sql_constraints = [
        (
            'company_picking_type_unique',
            'unique(company_id, picking_type_id)',
            'An Operation Type can only be configured once per company.',
        ),
    ]

    @api.constrains('company_id', 'document_kind', 'picking_type_id')
    def _check_operation_type(self):
        for config in self:
            picking_type = config.picking_type_id
            if picking_type.code != 'internal':
                raise ValidationError(_(
                    'BG/RBG requires an Internal Transfer Operation Type.'
                ))
            if picking_type.company_id and picking_type.company_id != config.company_id:
                raise ValidationError(_(
                    'The Operation Type must belong to the configured company.'
                ))
            if (
                config.document_kind == 'loan'
                and picking_type.reservation_method != 'manual'
            ):
                raise ValidationError(_(
                    'The BG Operation Type must already use Manual reservation. '
                    'This module does not change the Operation Type settings.'
                ))