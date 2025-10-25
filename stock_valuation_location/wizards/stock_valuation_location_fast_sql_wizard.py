from odoo import api, fields, models, _
from odoo.exceptions import UserError

class StockValuationLocationFastSQLWizard(models.TransientModel):
    _name = "stock.valuation.location.fast.sql.wizard"
    _description = "Fast SQL Recompute (SVL.location_id)"

    dry_run = fields.Boolean(default=True, help="If enabled, does not update. Only show affected count.")
    limit = fields.Integer(default=10000, help="0 means no limit. Recommended: 10000-50000 for incremental updates.")
    lock_key = fields.Integer(default=827174, help="Advisory lock key to avoid concurrent runs.")
    timeout = fields.Integer(default=300, help="Query timeout in seconds (default: 300 = 5 minutes)")

    result_msg = fields.Text(readonly=True)

    def action_run(self):
        limit = self.limit or None
        res = self.env["stock.valuation.layer"].with_context()._sql_fast_fill_location(
            dry_run=self.dry_run, 
            limit=limit, 
            lock_key=self.lock_key,
            timeout=self.timeout
        )
        msg = _(
            "Fast SQL path executed.\n"
            "Dry run: %(dry)s\n"
            "Limited: %(lim)s\n"
            "Affected rows: %(cnt)s\n\n"
            "%(note)s",
            dry="Yes" if res["dry_run"] else "No",
            lim="Yes" if res["limited"] else "No",
            cnt=res["count"],
            note="Note: Run multiple times with limit until count reaches 0." if res["limited"] and not res["dry_run"] else ""
        )
        self.write({"result_msg": msg})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "name": _("SVL Location — Fast SQL Result"),
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
