from odoo import api, fields, models, _
from odoo.exceptions import UserError

class StockValuationLocationFastSQLWizard(models.TransientModel):
    _name = "stock.valuation.location.fast.sql.wizard"
    _description = "Fast SQL Recompute (SVL.location_id)"

    dry_run = fields.Boolean(default=True, help="If enabled, does not update. Only show affected count.")
    # Defaults tuned for large databases (e.g. 300k+ SVL records)
    limit = fields.Integer(default=20000, help="0 means no limit. Recommended: 20000 for large DBs; adjust down if low memory.")
    lock_key = fields.Integer(default=827174, help="Advisory lock key to avoid concurrent runs.")
    # Use a larger default timeout to allow bigger batches to complete on slower systems
    timeout = fields.Integer(default=600, help="Query timeout in seconds (default: 600 = 10 minutes)")

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
