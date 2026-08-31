import uuid

from odoo import api, fields, models, _
from odoo.exceptions import UserError


BUILTIN_OUTCOME_CODES = {
    'repaired',
    'parts_replaced',
    'asset_replaced',
    'retired',
    'no_repair',
}


class ITAssetRepairOutcome(models.Model):
    _name = 'buz.it.asset.repair.outcome'
    _description = 'IT Asset Repair Outcome'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    code = fields.Char(required=True, readonly=True, copy=False, index=True)
    behavior = fields.Selection([
        ('generic', 'General Outcome'),
        ('parts_replaced', 'Parts Replaced'),
        ('asset_replaced', 'Asset Replaced'),
        ('retired', 'Retired'),
    ], required=True, readonly=True, default='generic', copy=False)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The internal Outcome code must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            requested_code = vals.get('code')
            if requested_code not in BUILTIN_OUTCOME_CODES:
                vals['code'] = 'custom_%s' % uuid.uuid4().hex
                vals['behavior'] = 'generic'
        return super().create(vals_list)

    def write(self, vals):
        # อนุญาตให้ Odoo โหลดค่า built-in ซ้ำระหว่างติดตั้ง/อัปเกรดเท่านั้น
        is_module_loading = (
            self.env.is_superuser()
            and self.env.context.get('install_mode')
        )
        if {'code', 'behavior'}.intersection(vals) and not is_module_loading:
            raise UserError(_('Outcome code and behavior cannot be changed.'))
        return super().write(vals)

    def unlink(self):
        ticket_model = self.env['buz.helpdesk.ticket']
        if ticket_model.search_count([('repair_outcome_id', 'in', self.ids)]):
            raise UserError(_('Outcomes used by Tickets must be archived.'))
        return super().unlink()
