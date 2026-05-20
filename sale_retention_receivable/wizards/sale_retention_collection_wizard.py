from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleRetentionCollectionWizard(models.TransientModel):
    _name = "sale.retention.collection.wizard"
    _description = "Collect Retention Receivable"

    partner_id = fields.Many2one("res.partner", string="Customer", required=True,
                                 domain="[('sale_retention_enabled', '=', True)]")
    retention_line_ids = fields.One2many(
        "sale.retention.collection.wizard.line",
        "wizard_id",
        string="Retention Items",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Bank Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        required=True,
    )
    bank_account_id = fields.Many2one(
        "account.account",
        string="Bank Account",
        domain="[('deprecated', '=', False), ('account_type', 'in', ('asset_cash', 'asset_current'))]",
        required=True,
    )
    payment_date = fields.Date(
        string="Payment Date",
        required=True,
        default=fields.Date.context_today,
    )
    total_to_collect = fields.Monetary(
        string="Total to Collect",
        compute="_compute_total_to_collect",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        active_ids = self.env.context.get("active_ids", [])
        active_model = self.env.context.get("active_model")

        if active_model == "sale.retention.receivable" and active_ids:
            retentions = self.env["sale.retention.receivable"].browse(active_ids).filtered(
                lambda r: r.state in ("open", "partially_collected")
            )
            if retentions:
                partners = retentions.mapped("partner_id")
                if len(partners) == 1:
                    vals["partner_id"] = partners.id
                vals["retention_line_ids"] = [
                    (0, 0, self._prepare_retention_line_vals(line))
                    for line in retentions
                ]

        if not vals.get("journal_id"):
            journal = self.env["account.journal"].search(
                [("type", "in", ["bank", "cash"]), ("company_id", "=", self.env.company.id)],
                limit=1,
            )
            if journal:
                vals["journal_id"] = journal.id
                if journal.default_account_id:
                    vals["bank_account_id"] = journal.default_account_id.id
        return vals

    def _prepare_retention_line_vals(self, line):
        return {
            "retention_id": line.id,
            "collect_amount": line.balance_amount,
        }

    @api.depends("retention_line_ids.collect_amount")
    def _compute_total_to_collect(self):
        for wizard in self:
            wizard.total_to_collect = sum(
                wizard.retention_line_ids.mapped("collect_amount")
            )

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        """Load open/open retention lines for the selected partner."""
        if self.partner_id:
            lines = self.env["sale.retention.receivable"].search([
                ("partner_id", "=", self.partner_id.id),
                ("state", "in", ("open", "partially_collected")),
            ])
            self.retention_line_ids = [
                (5, 0),
            ] + [
                (0, 0, self._prepare_retention_line_vals(line))
                for line in lines
            ]
        else:
            self.retention_line_ids = [(5, 0)]

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        if self.journal_id and self.journal_id.default_account_id:
            self.bank_account_id = self.journal_id.default_account_id

    def action_collect(self):
        """Create payment entry and update retention records."""
        self.ensure_one()

        if not self.retention_line_ids:
            raise UserError(_("Please select at least one retention item to collect."))

        if not self.journal_id:
            raise UserError(_("Please select a bank journal."))

        if not self.bank_account_id:
            raise UserError(_("Please select a bank account."))

        if self.total_to_collect <= 0:
            raise UserError(_("Total collection amount must be greater than zero."))

        move_ctx = dict(self.env.context)
        move_ctx.pop("default_move_type", None)
        move_ctx.pop("move_type", None)
        AccountMove = self.env["account.move"].with_context(move_ctx)

        for line in self.retention_line_ids:
            if line.collect_amount <= 0:
                raise UserError(
                    _("Collection amount for %s must be greater than zero.",
                      line.retention_id.display_name)
                )
            if line.collect_amount > line.balance_amount:
                raise UserError(
                    _("Collection amount (%.2f) exceeds outstanding balance (%.2f) for %s.",
                      line.collect_amount, line.balance_amount, line.retention_id.display_name)
                )

        # Create a single bank journal entry for all collections
        # Debit: Bank account
        # Credit: Retention Receivable accounts (one line per retention account)
        move_vals = {
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "date": self.payment_date,
            "ref": _("Retention Collection - %s", self.partner_id.display_name),
            "line_ids": [],
        }

        # Bank line (debit)
        bank_account = self.bank_account_id

        move_vals["line_ids"].append((0, 0, {
            "name": _("Retention collection"),
            "account_id": bank_account.id,
            "partner_id": self.partner_id.id,
            "debit": self.total_to_collect,
            "credit": 0.0,
        }))

        # Retention credit lines grouped by account
        for line in self.retention_line_ids:
            retention = line.retention_id
            account = retention.retention_account_id
            if not account:
                raise UserError(_("Retention record %s has no retention account.", retention.display_name))

            move_vals["line_ids"].append((0, 0, {
                "name": _("Retention: %s", retention.display_name),
                "account_id": account.id,
                "partner_id": self.partner_id.id,
                "debit": 0.0,
                "credit": line.collect_amount,
            }))

        move = AccountMove.create(move_vals)
        move.action_post()

        # Update retention records
        for line in self.retention_line_ids:
            retention = line.retention_id
            new_collected = retention.collected_amount + line.collect_amount
            new_balance = retention.retention_amount - new_collected

            vals = {
                "collected_amount": new_collected,
                "collection_move_ids": [(4, move.id)],
            }

            if retention.currency_id.compare_amounts(new_balance, 0.0) <= 0:
                vals["state"] = "collected"
            else:
                vals["state"] = "partially_collected"

            retention.write(vals)

        return {
            "type": "ir.actions.act_window_close",
        }


class SaleRetentionCollectionWizardLine(models.TransientModel):
    _name = "sale.retention.collection.wizard.line"
    _description = "Retention Collection Line"

    wizard_id = fields.Many2one("sale.retention.collection.wizard", string="Wizard",
                                required=True, ondelete="cascade")
    retention_id = fields.Many2one("sale.retention.receivable", string="Retention",
                                   required=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        related="retention_id.partner_id",
        readonly=True,
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
        related="retention_id.invoice_id",
        readonly=True,
    )
    invoice_date = fields.Date(
        string="Invoice Date",
        related="retention_id.invoice_date",
        readonly=True,
    )
    due_date = fields.Date(
        string="Due Date",
        related="retention_id.retention_due_date",
        readonly=True,
    )
    retention_amount = fields.Monetary(
        string="Retention Amount",
        related="retention_id.retention_amount",
        readonly=True,
    )
    collected_amount = fields.Monetary(
        string="Collected",
        related="retention_id.collected_amount",
        readonly=True,
    )
    balance_amount = fields.Monetary(
        string="Balance",
        related="retention_id.balance_amount",
        readonly=True,
    )
    collect_amount = fields.Monetary(string="Collect Amount", required=True)
    currency_id = fields.Many2one("res.currency", related="retention_id.currency_id")
