# Copyright (C) 2018 - TODAY, Pavlov Media
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class Partner(models.Model):
    _inherit = "res.partner"

    agreement_ids = fields.One2many("agreement", "partner_id", string="Agreements")
    agreements_count = fields.Integer(compute="_compute_agreements_count")

    @api.model
    def _name_search(
        self, name="", args=None, operator="ilike", limit=100, order=None
    ):
        if self.env.context.get("agreement_partner_code"):
            domain = list(args or []) + [("ref", "=like", "C%")]
            if name:
                domain.append(("ref", operator, name))
            return self._search(domain, limit=limit, order=order)
        return super()._name_search(name, args, operator, limit, order)

    def name_get(self):
        if self.env.context.get("agreement_partner_code"):
            return [(partner.id, partner.ref or partner.display_name) for partner in self]
        return super().name_get()

    @api.depends("agreement_ids")
    def _compute_agreements_count(self):
        domain = [("partner_id", "in", self.ids)]
        res = self.env["agreement"].read_group(
            domain=domain, fields=["partner_id"], groupby=["partner_id"]
        )
        agreement_dict = {x["partner_id"][0]: x["partner_id_count"] for x in res}
        for rec in self:
            rec.agreements_count = agreement_dict.get(rec.id, 0)

    def action_open_agreement(self):
        self.ensure_one()
        action = self.env.ref("agreement.agreement_action")
        result = action.read()[0]
        result["domain"] = [("partner_id", "=", self.id)]
        result["context"] = {"default_partner_id": self.id}
        return result
