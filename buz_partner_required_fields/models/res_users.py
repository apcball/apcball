from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def copy(self, default=None):
        # Duplicating a user creates its delegated res.partner via _inherits,
        # which would trip _validate_required_fields. Skip validation for the
        # whole copy flow.
        return super(
            ResUsers, self.with_context(skip_partner_required_fields=True)
        ).copy(default)
