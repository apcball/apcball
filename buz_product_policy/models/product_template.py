from odoo import models, fields, api, _
from odoo.exceptions import AccessError


RESTRICTED_POLICY_FIELDS = {'sale_ok', 'purchase_ok', 'can_be_expensed', 'can_be_pos'}


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    can_be_expensed = fields.Boolean(string='Can be Expensed', default=False)

    is_product_policy_readonly = fields.Boolean(
        compute='_compute_is_product_policy_readonly'
    )

    @api.depends_context('uid')
    def _compute_is_product_policy_readonly(self):
        is_manager = self.env.user.has_group(
            'buz_product_policy.group_product_manager'
        )
        for record in self:
            record.is_product_policy_readonly = not is_manager

    def write(self, values):
        restricted = RESTRICTED_POLICY_FIELDS & set(values.keys())
        if restricted and not self.env.user.has_group(
            'buz_product_policy.group_product_manager'
        ):
            raise AccessError(
                _('Only Product Managers can modify policy fields: %s')
                % ', '.join(sorted(restricted))
            )
        return super().write(values)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, values):
        restricted = RESTRICTED_POLICY_FIELDS & set(values.keys())
        if restricted and not self.env.user.has_group(
            'buz_product_policy.group_product_manager'
        ):
            raise AccessError(
                _('Only Product Managers can modify policy fields: %s')
                % ', '.join(sorted(restricted))
            )
        return super().write(values)
