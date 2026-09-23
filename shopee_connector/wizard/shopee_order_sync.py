from datetime import timedelta

from odoo import _, fields, models


class ShopeeOrderSyncWizard(models.TransientModel):
    _name = "shopee.order.sync.wizard"
    _description = "Sync Shopee Orders"

    def _default_config(self):
        return self.env["shopee.config"].search([("active", "=", True)], limit=1)

    config_id = fields.Many2one(
        "shopee.config", string="Shopee Shop", required=True,
        default=_default_config, domain="[('active', '=', True)]",
    )
    import_orders_from = fields.Datetime(
        string="Import Orders From", required=True,
        default=lambda self: fields.Datetime.now() - timedelta(days=7),
        help="Import Orders fetches every Shopee order created since this "
        "date. Orders already in Odoo are skipped.",
    )
    result_message = fields.Text(readonly=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], default="draft")

    def _done(self, message):
        self.write({"state": "done", "result_message": message})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_import_orders(self):
        self.ensure_one()
        self.config_id.import_orders_from = self.import_orders_from
        created = self.config_id.action_sync_orders()
        return self._done(
            _("Imported %(count)s new order(s) created since %(since)s.")
            % {"count": created, "since": self.import_orders_from}
        )

    def action_sync_status(self):
        self.ensure_one()
        updated = self.config_id.sync_order_statuses()
        return self._done(
            _("Updated the status (and payment details) of %s order(s).") % updated
        )
