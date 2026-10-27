from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

from ..models.lazada_export_helpers import ExportFormatError, orders_from_rows

_MAX_LISTED = 20


class LazadaBuyerAddressImportWizard(models.TransientModel):
    _name = "lazada.buyer.address.import.wizard"
    _inherit = "lazada.file.import.mixin"
    _description = "Import Lazada Buyer Addresses"

    file_data = fields.Binary(string="Seller Center Order File", required=True)
    file_name = fields.Char(string="Filename")
    state = fields.Selection(
        [("upload", "Upload"), ("done", "Done")], default="upload"
    )
    result_message = fields.Text(readonly=True)

    def _orders_from_file(self):
        """Return {order_number: /order/get-like dict} from the upload."""
        headers, rows = self._read_rows()
        try:
            orders = orders_from_rows(headers, rows)
        except ExportFormatError as exc:
            raise UserError(str(exc)) from exc
        if not orders:
            raise UserError(_("No orders were found in the file."))
        return orders

    def action_import(self):
        self.ensure_one()
        orders = self._orders_from_file()
        SaleOrder = self.env["sale.order"]
        tz = SaleOrder._lazada_local_tz()
        updated, taxed, not_found, skipped, failed, paid = [], [], [], [], [], []
        for number, detail in orders.items():
            sale_orders = SaleOrder.search([
                ("is_lazada_order", "=", True),
                "|", ("lazada_order_id", "=", number), ("client_order_ref", "=", number),
            ])
            if not sale_orders:
                not_found.append(number)
                continue
            status = SaleOrder._lazada_summary_status(detail["statuses"])
            for sale_order in sale_orders:
                try:
                    with self.env.cr.savepoint():
                        applied, has_tax, has_payment = self._apply_to_order(
                            sale_order, detail, status, tz
                        )
                except (UserError, ValidationError) as exc:
                    failed.append(f"{number} ({exc})")
                    continue
                # Only report what was actually saved (a failure rolls back).
                if has_tax:
                    taxed.append(number)
                if not applied:
                    skipped.append(number)
                    continue
                if has_payment:
                    paid.append(number)
                updated.append(number)

        self.write({
            "state": "done",
            "result_message": self._result_message(
                updated, taxed, not_found, skipped, failed, paid
            ),
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _apply_to_order(self, sale_order, detail, status, tz):
        """Apply one export order; returns (applied, taxed, paid).

        The user must be allowed to edit the order and its buyer. The update
        itself runs as superuser: other installed modules react to sales
        order changes with models Lazada staff cannot access (e.g. a finance
        delivery plan). ``sudo()`` keeps the uid, so the chatter still shows
        the user.
        """
        for record in (sale_order, sale_order.partner_id):
            record.check_access_rights("write")
            record.check_access_rule("write")
        order = sale_order.sudo()
        partner = order.partner_id
        config = order.lazada_config_id
        taxed = bool(
            detail["tax_code"] and config and partner.lazada_config_id == config
            and partner._lazada_apply_tax_invoice(detail, config)
        )
        if not order._lazada_apply_recipient(detail):
            return False, taxed, False
        if detail["created_at"] and status not in ("unpaid", "canceled"):
            order._lazada_set_commitment_date(tz.localize(detail["created_at"]))
        paid = bool(
            detail["payment"]
            and order.lazada_payment_source != "finance"
            and order._lazada_apply_payment(detail["payment"])
        )
        return True, taxed, paid

    @staticmethod
    def _listed(numbers):
        shown = ", ".join(numbers[:_MAX_LISTED])
        if len(numbers) > _MAX_LISTED:
            shown += f" … (+{len(numbers) - _MAX_LISTED})"
        return shown

    def _result_message(self, updated, taxed, not_found, skipped, failed, paid=()):
        lines = [_("Updated buyer address for %s order(s).") % len(updated)]
        if paid:
            lines.append(
                _("Payment details (shipping, seller discount) applied for %s "
                  "order(s).") % len(paid)
            )
        if taxed:
            lines.append(
                _("Tax invoice data (Tax ID, invoice address) applied for %s "
                  "order(s): %s") % (len(taxed), self._listed(taxed))
            )
        if not_found:
            lines.append(
                _("%s order(s) are not in Odoo yet (import them first): %s")
                % (len(not_found), self._listed(not_found))
            )
        if skipped:
            lines.append(
                _("%s order(s) skipped because the customer is not a Lazada "
                  "buyer contact: %s") % (len(skipped), self._listed(skipped))
            )
        if failed:
            lines.append(
                _("%s order(s) failed: %s") % (len(failed), self._listed(failed))
            )
        return "\n".join(lines)
