# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FifoRecalculationConfig(models.Model):
    """Scope for the scheduled FIFO queue check.

    The scheduled run reports; it never writes. The fields that used to make it
    write unattended — auto_apply, clear_old_layers, lock_after_recal — are
    gone.
    """
    _name = 'fifo.recalculation.config'
    _description = 'FIFO Recalculation Configuration'

    name = fields.Char(string='Config Name', required=True)
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(
        string='Default Config',
        help='Used by the scheduled action when no specific config is given.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Warehouses',
        required=True,
        help='Required. Without it the scheduled check has no scope and does '
             'nothing.'
    )
    product_ids = fields.Many2many('product.product', string='Products')
    product_categ_ids = fields.Many2many('product.category', string='Product Categories')
    notification_user_ids = fields.Many2many(
        'res.users',
        string='Notify Users',
        help='Who receives the report. With nobody here the check runs and the '
             'result is never seen.'
    )

    @api.constrains('is_default')
    def _check_single_default(self):
        """Ensure only one default config per company."""
        for record in self:
            if record.is_default:
                other_defaults = self.search([
                    ('id', '!=', record.id),
                    ('company_id', '=', record.company_id.id),
                    ('is_default', '=', True)
                ])
                if other_defaults:
                    raise ValidationError(_(
                        'Only one default configuration is allowed per company.'
                    ))
