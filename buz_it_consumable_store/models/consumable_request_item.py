from odoo import _, api, fields, models


class BuzItConsumableRequestItem(models.Model):
    _inherit = 'buz.it.consumable'

    in_current_cart = fields.Boolean(
        compute='_compute_in_current_cart',
        string='ในรายการเบิกแล้ว',
    )

    @api.depends_context('uid', 'company')
    def _compute_in_current_cart(self):
        draft = self.env['buz.it.consumable.request'].search([
            ('state', '=', 'draft'),
            ('requester_id', '=', self.env.uid),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        in_cart = set(draft.line_ids.mapped('consumable_id').ids) if draft else set()
        for rec in self:
            rec.in_current_cart = rec.id in in_cart

    def action_add_to_cart(self):
        self.ensure_one()
        return {
            'name': _('เพิ่มในรายการเบิก'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.it.consumable.add.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_consumable_id': self.id},
        }

