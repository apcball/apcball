from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    date_approve = fields.Datetime(readonly=False)

    @api.model
    def get_import_templates(self):
        return [{
            'label': _('Import Template for Purchase Orders'),
            'template': 'import_purchase_template/static/xls/purchase_order_template.xlsx'
        }]
