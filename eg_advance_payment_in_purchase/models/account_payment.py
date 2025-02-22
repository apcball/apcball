from odoo import models, fields, api, _


class AccountPayment(models.Model):
    _inherit = "account.payment"

    purchase_id = fields.Many2one(comodel_name="purchase.order", string="Purchase Order")

    @api.model
    def create(self, vals):
        res = super(AccountPayment, self).create(vals)
        if 'ref' in vals:
            purchase_id = self.env["purchase.order"].search([("name", "=", vals['ref'])], limit=1)
            if purchase_id and not res.purchase_id:
                res.purchase_id = purchase_id.id
            invoice_id = self.env["account.move"].search([("name", "=", vals['ref'])], limit=1)
            if invoice_id and not res.purchase_id:
                purchase_id = self.env["purchase.order"].search([("name", "=", invoice_id.origin)], limit=1)
                if purchase_id:
                    res.purchase_id = purchase_id.id
        return res