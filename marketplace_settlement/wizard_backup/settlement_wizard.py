from odoo import api, fields, models, _
from odoo.exceptions import UserError

class MarketplaceSettlementWizard(models.TransientModel):
    _name = "marketplace.settlement.wizard.simple"
    _description = "Simple Marketplace Settlement Wizard"

    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    date = fields.Date(string="Settlement Date", default=fields.Date.context_today, required=True)
    date_from = fields.Date(string="Invoice Date From")
    date_to = fields.Date(string="Invoice Date To")
    journal_id = fields.Many2one(
        "account.journal",
        string="Clearing Journal",
        domain="[('type','=','general'),('company_id','=',company_id)]",
        required=True,
    )
    marketplace_partner_id = fields.Many2one(
        "res.partner",
        string="Marketplace Partner (e.g., Shopee)",
        required=True,
        help="Who actually pays you (Shopee/Lazada). The grouped receivable will be moved to this partner."
    )
    settlement_ref = fields.Char(string="Settlement Ref/No.", help="e.g., SHOPEE-SETT-2025-08-29")
    trade_channel = fields.Selection([
        ("shopee", "Shopee"),
        ("lazada", "Lazada"),
        ("nocnoc", "Noc Noc"),
        ("tiktok", "Tiktok"),
        ("other", "Other"),
    ], string="Trade Channel", help="Filter invoices by trade channel when adding lines.")
    currency_id = fields.Many2one(related="company_id.currency_id", store=False, readonly=True)
    line_ids = fields.One2many("marketplace.settlement.line.simple", "wizard_id", string="Invoices to Settle")
    
    # Deduction fields
    fee_amount = fields.Monetary('Marketplace Fee', currency_field='currency_id')
    fee_account_id = fields.Many2one('account.account', string='Fee Account')
    vat_on_fee_amount = fields.Monetary('VAT on Fee', currency_field='currency_id')
    vat_account_id = fields.Many2one('account.account', string='VAT Account')
    wht_amount = fields.Monetary('Withholding Tax (WHT)', currency_field='currency_id')
    wht_account_id = fields.Many2one('account.account', string='WHT Account')
    
    # Deduction fields
    fee_amount = fields.Monetary('Marketplace Fee', currency_field='currency_id')
    fee_account_id = fields.Many2one('account.account', string='Fee Account')
    vat_on_fee_amount = fields.Monetary('VAT on Fee', currency_field='currency_id')
    vat_account_id = fields.Many2one('account.account', string='VAT Account')
    wht_amount = fields.Monetary('Withholding Tax (WHT)', currency_field='currency_id')
    wht_account_id = fields.Many2one('account.account', string='WHT Account')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_model = self._context.get("active_model")
        active_ids = self._context.get("active_ids") or []
        lines = []
        if active_model == "account.move" and active_ids:
            moves = self.env["account.move"].browse(active_ids).filtered(
                lambda m: m.company_id == self.env.company
                and m.is_invoice()
                and m.state == "posted"
                and m.payment_state in ("not_paid", "partial")
            )
            for inv in moves:
                lines.append((0, 0, {
                    "invoice_id": inv.id,
                    "partner_id": inv.partner_id.id,
                    "residual_company": abs(inv.amount_residual_signed if inv.company_id.currency_id == inv.currency_id else inv.amount_residual),
                    "amount": abs(inv.amount_residual),  # in invoice currency
                    "currency_id": inv.currency_id.id,
                }))
        if lines:
            res["line_ids"] = lines
        # sensible default journal
        j = self.env["account.journal"].search([("type","=","general"), ("company_id","=",self.env.company.id)], limit=1)
        if j:
            res["journal_id"] = j.id
        return res

    @api.onchange('trade_channel')
    def _onchange_trade_channel(self):
        # When trade_channel is selected, restrict the invoice selection in the one2many lines
        if self.trade_channel:
            domain = [
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('state', '=', 'posted'),
                ('trade_channel', '=', self.trade_channel),
                ('amount_residual', '!=', 0.0),
            ]
            return {'domain': {'line_ids.invoice_id': domain}}
        # clear domain if not set
        return {'domain': {'line_ids.invoice_id': [('move_type','in',['out_invoice','out_refund'])]}}

    def _validate_inputs(self):
        if not self.line_ids:
            raise UserError(_("No invoices selected."))
        if any(l.amount <= 0 for l in self.line_ids):
            raise UserError(_("Each line amount must be greater than zero."))
        
        # Validate deduction accounts if amounts are provided
        if self.fee_amount and not self.fee_account_id:
            raise UserError(_('Please specify Fee Account for marketplace fee.'))
        if self.vat_on_fee_amount and not self.vat_account_id:
            raise UserError(_('Please specify VAT Account for VAT on fee.'))
        if self.wht_amount and not self.wht_account_id:
            raise UserError(_('Please specify WHT Account for withholding tax.'))

    def action_create_entry(self):
        self._validate_inputs()
        company = self.company_id
        mp_partner = self.marketplace_partner_id
        receivable_account = mp_partner.property_account_receivable_id
        if not receivable_account or receivable_account.company_id != company:
            raise UserError(_("Marketplace partner must have a Receivable account in company %s.") % company.display_name)

        aml_vals = []
        to_reconcile_map = {}  # invoice.id -> aml created

        # Compute the total in company currency & build counterpart lines per invoice
        total_company = 0.0
        for line in self.line_ids:
            inv = line.invoice_id
            if inv.company_id != company:
                raise UserError(_("Invoice %s is not in company %s.") % (inv.display_name, company.display_name))
            # Determine open receivable AML(s) on invoice
            inv_recv = inv.line_ids.filtered(lambda a: a.account_id.account_type == 'asset_receivable' and not a.reconciled)
            if not inv_recv:
                continue

            # amount_to_settle in invoice currency, sign-safe
            amount_invoice_cur = min(line.amount, abs(inv.amount_residual))  # don't exceed residual
            if amount_invoice_cur <= 0:
                continue

            # convert to company currency at invoice rate on invoice date
            amount_company_cur = inv.currency_id._convert(
                amount_invoice_cur, company.currency_id, company, inv.invoice_date or inv.date or fields.Date.context_today(self)
            )

            # Determine sign: for customer invoice (debit open), we need a credit; for refunds we need a debit
            # Heuristic: sum of open receivable balances in company currency tells the sign.
            open_balance = sum(inv_recv.mapped("amount_residual"))
            # open_balance is in company currency; positive means debit balance
            if open_balance > 0:
                # normal invoice -> create CREDIT to clear
                aml_vals.append({
                    "name": inv.name or inv.ref or inv.payment_reference or _("Settlement %s") % (self.settlement_ref or ""),
                    "account_id": inv_recv[0].account_id.id,
                    "partner_id": inv.partner_id.id,
                    "credit": amount_company_cur,
                    "debit": 0.0,
                    "currency_id": inv.currency_id.id if inv.currency_id != company.currency_id else False,
                    "amount_currency": -amount_invoice_cur if inv.currency_id != company.currency_id else 0.0,
                })
                total_company += amount_company_cur
            else:
                # refund -> create DEBIT to clear
                aml_vals.append({
                    "name": inv.name or inv.ref or inv.payment_reference or _("Settlement %s") % (self.settlement_ref or ""),
                    "account_id": inv_recv[0].account_id.id,
                    "partner_id": inv.partner_id.id,
                    "debit": amount_company_cur,
                    "credit": 0.0,
                    "currency_id": inv.currency_id.id if inv.currency_id != company.currency_id else False,
                    "amount_currency": amount_invoice_cur if inv.currency_id != company.currency_id else 0.0,
                })
                total_company -= amount_company_cur  # note: refunds reduce the needed debit

            to_reconcile_map.setdefault(inv.id, 0.0)
            to_reconcile_map[inv.id] += amount_company_cur if open_balance > 0 else -amount_company_cur

        if not aml_vals:
            raise UserError(_("Nothing to settle. Check residuals."))

        # Add deduction lines
        total_deductions = 0.0
        
        # Marketplace Fee
        if self.fee_amount and self.fee_amount > 0:
            aml_vals.append({
                "name": _('Marketplace Fee - %s') % name,
                "account_id": self.fee_account_id.id,
                "partner_id": mp_partner.id,
                "debit": self.fee_amount,
                "credit": 0.0,
            })
            total_deductions += self.fee_amount

        # VAT on Fee
        if self.vat_on_fee_amount and self.vat_on_fee_amount > 0:
            aml_vals.append({
                "name": _('VAT on Marketplace Fee - %s') % name,
                "account_id": self.vat_account_id.id,
                "partner_id": mp_partner.id,
                "debit": self.vat_on_fee_amount,
                "credit": 0.0,
            })
            total_deductions += self.vat_on_fee_amount

        # Withholding Tax (WHT)
        if self.wht_amount and self.wht_amount > 0:
            aml_vals.append({
                "name": _('Withholding Tax - %s') % name,
                "account_id": self.wht_account_id.id,
                "partner_id": mp_partner.id,
                "debit": self.wht_amount,
                "credit": 0.0,
            })
            total_deductions += self.wht_amount

        # Adjust total_company for deductions
        total_company_adjusted = total_company - total_deductions

        # Build balancing line to marketplace receivable
        name = self.settlement_ref or _("Marketplace Settlement")
        # total_company_adjusted currently equals sum(credits) - sum(debits) on counterpart lines minus deductions
        # We need the opposite on the MP line to balance the entry.
        if total_company_adjusted > 0:
            # counterpart lines are overall CREDIT > DEBIT -> we need a DEBIT to MP
            mp_debit = total_company_adjusted
            mp_credit = 0.0
            amount_currency = 0.0
        else:
            mp_debit = 0.0
            mp_credit = -total_company_adjusted
            amount_currency = 0.0

        aml_vals.append({
            "name": name,
            "account_id": receivable_account.id,
            "partner_id": mp_partner.id,
            "debit": mp_debit,
            "credit": mp_credit,
            "currency_id": False,
            "amount_currency": 0.0,
        })

        move_vals = {
            "date": self.date,
            "journal_id": self.journal_id.id,
            "ref": name,
            "line_ids": [(0, 0, v) for v in aml_vals],
            "company_id": company.id,
        }
        move = self.env["account.move"].create(move_vals)
        move.action_post()

        # Reconcile per invoice: match the wizard line (same account/partner) with open aml on invoice
        for inv in self.line_ids.mapped("invoice_id"):
            inv_recv_open = inv.line_ids.filtered(lambda a: a.account_id.account_type == 'asset_receivable' and not a.reconciled)
            if not inv_recv_open:
                continue
            # Find the AML we just created for this partner/account with the same sign side
            created_lines = move.line_ids.filtered(
                lambda a: a.account_id == inv_recv_open[0].account_id and a.partner_id == inv.partner_id and not a.reconciled
            )
            # Try reconcile in reasonable pairs (there may be multiple open lines if partials exist)
            for created in created_lines:
                # find a matching open line from invoice with opposite sign that still has residual
                candidate = inv_recv_open.filtered(lambda a: (a.debit > 0 and created.credit > 0) or (a.credit > 0 and created.debit > 0))
                if candidate:
                    (candidate[:1] + created).reconcile()  # reconcile first match

        action = self.env.ref("account.action_move_journal_line").read()[0]
        action["domain"] = [("id", "=", move.id)]
        return action


class MarketplaceSettlementLine(models.TransientModel):
    _name = "marketplace.settlement.line.simple"
    _description = "Simple Marketplace Settlement Line"

    wizard_id = fields.Many2one("marketplace.settlement.wizard.simple", required=True, ondelete="cascade")
    invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
        required=True,
        domain="[('move_type','in',['out_invoice','out_refund']), ('state','=','posted'), ('amount_residual','!=',0.0)]",
    )
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    currency_id = fields.Many2one("res.currency", required=True)
    amount = fields.Monetary(string="Amount to settle (invoice currency)", required=True)
    residual_company = fields.Monetary(string="Residual (company currency)", currency_field="company_currency_id", readonly=True)
    company_currency_id = fields.Many2one(related="wizard_id.company_id.currency_id", store=False, readonly=True)

    @api.onchange("invoice_id")
    def _onchange_invoice_id(self):
        for rec in self:
            if rec.invoice_id:
                rec.partner_id = rec.invoice_id.partner_id
                rec.currency_id = rec.invoice_id.currency_id
                rec.amount = abs(rec.invoice_id.amount_residual)
                rec.residual_company = abs(rec.invoice_id.amount_residual_signed if rec.invoice_id.company_currency_id == rec.invoice_id.currency_id else rec.invoice_id.amount_residual)
