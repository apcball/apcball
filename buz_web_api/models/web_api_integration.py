from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WebApiIntegration(models.Model):
    _name = 'web.api.integration'
    _description = 'Web API Integration'
    _order = 'name'

    name = fields.Char(string='Integration Name', required=True)
    user_id = fields.Many2one(
        'res.users',
        string='Odoo User',
        required=True,
        default=lambda self: self.env.user,
        domain=[('share', '=', False), ('active', '=', True)],
        ondelete='restrict',
    )
    key_name = fields.Char(
        string='Native API Key Name',
        readonly=True,
        copy=False,
    )
    active = fields.Boolean(default=True)
    last_generated_at = fields.Datetime(string='Last Generated At', readonly=True, copy=False)

    _sql_constraints = [
        (
            'web_api_integration_name_uniq',
            'unique(name)',
            'The integration name must be unique.',
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.key_name:
                record.key_name = f'Web API: {record.name}'
        return records

    def _check_integration_user(self):
        self.ensure_one()
        if not self.user_id.active or self.user_id.share:
            raise ValidationError(_('The integration user must be an active internal user.'))

    def _native_keys(self):
        self.ensure_one()
        return self.env['res.users.apikeys'].sudo().search([
            ('user_id', '=', self.user_id.id),
            ('name', '=', self.key_name),
        ])

    def _revoke_native_keys(self):
        self.ensure_one()
        keys = self._native_keys()
        if keys:
            keys._remove()

    def action_generate_api_key(self):
        self.ensure_one()
        self._check_integration_user()
        if not self.active:
            raise ValidationError(_('Activate the integration before generating an API key.'))

        self._revoke_native_keys()
        key = self.env['res.users.apikeys'].with_user(self.user_id)._generate(None, self.key_name)
        self.write({'last_generated_at': fields.Datetime.now()})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'web.api.key.show',
            'name': _('API Key Ready'),
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_key': key,
                'default_integration_name': self.name,
                'default_user_login': self.user_id.login,
            },
        }

    def action_revoke_api_key(self):
        for record in self:
            record._revoke_native_keys()
        return True

    def unlink(self):
        for record in self:
            record._revoke_native_keys()
        return super().unlink()
