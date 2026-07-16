# -*- coding: utf-8 -*-

from odoo import _, fields, models


class WarrantyCard(models.Model):
    _inherit = 'warranty.card'

    service_receipt_ids = fields.One2many(
        'service.receipt',
        'warranty_card_id',
        string='Service Claims',
        domain=[('service_case_type', '=', 'replacement')],
    )
    service_receipt_count = fields.Integer(
        string='Service Claim Count',
        related='claim_count',
    )

    def action_view_claims(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Claims'),
            'res_model': 'service.receipt',
            'view_mode': 'tree,form',
            'domain': [('warranty_card_id', '=', self.id)],
            'context': {
                'default_warranty_card_id': self.id,
                'default_service_case_type': 'replacement',
            },
        }
