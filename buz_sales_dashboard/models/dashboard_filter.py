from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class SalesDashboardFilter(models.Model):
    """A user's own saved set of dashboard filters."""

    _name = "buz.sales.dashboard.filter"
    _description = "Sales Dashboard Saved Filter"
    _order = "name, id"

    name = fields.Char(required=True)
    user_id = fields.Many2one(
        "res.users", required=True, readonly=True, index=True, ondelete="cascade",
        default=lambda self: self.env.uid)
    filters = fields.Json()
    is_default = fields.Boolean()

    def _clean_vals(self, vals):
        vals = dict(vals)
        if not self.env.su and vals.get("user_id", self.env.uid) != self.env.uid:
            raise AccessError(_("ชุดตัวกรองเป็นของส่วนตัว สร้างแทนผู้อื่นไม่ได้"))
        if "filters" in vals:
            vals["filters"] = self.env["buz.sales.dashboard.report"]._sanitize_filters(
                vals["filters"])
        return vals

    def _keep_single_default(self):
        for record in self.filtered("is_default"):
            self.sudo().search([
                ("user_id", "=", record.user_id.id),
                ("is_default", "=", True),
                ("id", "!=", record.id),
            ]).is_default = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create([self._clean_vals(vals) for vals in vals_list])
        records._keep_single_default()
        return records

    def write(self, vals):
        result = super().write(self._clean_vals(vals))
        if vals.get("is_default"):
            self._keep_single_default()
        return result
