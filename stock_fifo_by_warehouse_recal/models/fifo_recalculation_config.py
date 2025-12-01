# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FifoRecalculationConfig(models.Model):
    """Configuration for scheduled FIFO recalculation."""
    _name = 'fifo.recalculation.config'
    _description = 'FIFO Recalculation Configuration'

    name = fields.Char(
        string='Config Name',
        required=True
    )
    active = fields.Boolean(
        default=True
    )
    is_default = fields.Boolean(
        string='Default Config',
        help='Use this config for scheduled actions when no specific config is provided'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    date_from = fields.Datetime(
        string='Start Date',
        help='Leave empty to use current date'
    )
    date_to = fields.Datetime(
        string='End Date',
        help='Leave empty to use current date'
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Warehouses'
    )
    product_ids = fields.Many2many(
        'product.product',
        string='Products'
    )
    product_categ_ids = fields.Many2many(
        'product.category',
        string='Product Categories'
    )
    clear_old_layers = fields.Selection([
        ('none', 'Do not touch existing layers'),
        ('range', 'Delete & Rebuild in selected date range'),
        ('all_product', 'Delete all layers for selected products'),
    ], string='Existing Layers Handling', default='range')
    lock_after_recal = fields.Boolean(
        string='Lock new layers',
        default=True
    )
    batch_size = fields.Integer(
        string='Batch Size',
        default=100
    )
    auto_apply = fields.Boolean(
        string='Auto Apply',
        default=False,
        help='If checked, recalculation will be applied automatically without preview'
    )
    notification_user_ids = fields.Many2many(
        'res.users',
        string='Notify Users',
        help='Users to notify after scheduled recalculation'
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
