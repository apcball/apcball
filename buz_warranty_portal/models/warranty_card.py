from odoo import models


class WarrantyCard(models.Model):
    _inherit = 'warranty.card'

    # Fields moved to buz_warranty_management (base model).
    # This inherit is kept for future portal-only additions.
    pass
