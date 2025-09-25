
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class EmployeeAdvanceBox(models.Model):
    _name = "employee.advance.box"
    _description = "Employee Advance Box"
    _order = "employee_id"
    _rec_name = "display_name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    employee_id = fields.Many2one(
        "hr.employee", 
        required=True, 
        index=True, 
        ondelete="cascade",
        string="Employee",
        tracking=True
    )
    account_id = fields.Many2one(
        "account.account",
        required=True,
        domain=[("account_type", "in", ["asset_current", "asset_non_current"])],
        string="Advance Account (141101)",
        help="Asset account used for employee advance, e.g., 141101",
        tracking=True
    )
    journal_id = fields.Many2one(
        "account.journal", 
        string="Default Bank/Cash Journal",
        domain=[("type", "in", ["cash", "bank"])],
        help="Default journal for advance top-up and settlement",
        tracking=True
    )
    currency_id = fields.Many2one(
        "res.currency", 
        default=lambda self: self.env.company.currency_id,
        string="Currency"
    )
    remember_base_amount = fields.Monetary(
        string="Base Amount Reference",
        currency_field="currency_id",
        default=0.0,
        help="Stored base amount used when refilling advances",
        tracking=True,
    )
    balance = fields.Monetary(
        compute="_compute_balance", 
        store=False,
        string="Current Balance"
    )
    display_name = fields.Char(
        compute="_compute_display_name", 
        store=True,
        string="Display Name"
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", 
        default=lambda self: self.env.company,
        string="Company"
    )

    @api.depends("employee_id", "account_id")
    def _compute_display_name(self):
        for box in self:
            if box.employee_id and box.account_id:
                box.display_name = f"{box.employee_id.name} - {box.account_id.code or box.account_id.name}"
            elif box.employee_id:
                box.display_name = box.employee_id.name
            else:
                box.display_name = _("New Advance Box")

    @api.depends("employee_id", "account_id")
    def _compute_balance(self):
        for box in self:
            bal = 0.0
            if box.employee_id and box.account_id:
                # Use employee's partner (user_partner_id) for journal entries
                partner = box.employee_id.user_partner_id
                if partner:
                    # Search for all posted journal entries for this partner and account
                    domain = [
                        ("account_id", "=", box.account_id.id),
                        ("partner_id", "=", partner.id),
                        ("parent_state", "=", "posted"),
                    ]
                    lines = self.env["account.move.line"].search(domain)
                    # Advance balance = debits - credits (positive means employee has advance)
                    bal = sum(line.debit - line.credit for line in lines)
            box.balance = bal

    @api.constrains("employee_id")
    def _check_unique_employee(self):
        for box in self:
            existing = self.search([
                ("employee_id", "=", box.employee_id.id),
                ("id", "!=", box.id),
                ("active", "=", True)
            ])
            if existing:
                raise ValidationError(_("An active advance box already exists for employee %s") % box.employee_id.name)

    @api.model
    def create_for_employee(self, employee_id):
        """Create advance box for employee if not exists"""
        existing = self.search([
            ("employee_id", "=", employee_id),
            ("active", "=", True)
        ], limit=1)
        if existing:
            return existing
        
        # Find default advance account (141101)
        advance_account = self.env["account.account"].search([
            ("code", "=like", "141101%"),
            ("company_id", "=", self.env.company.id)
        ], limit=1)
        
        if not advance_account:
            # Look for any current asset account
            advance_account = self.env["account.account"].search([
                ("account_type", "=", "asset_current"),
                ("company_id", "=", self.env.company.id)
            ], limit=1)
            
        if not advance_account:
            raise ValidationError(_("No suitable advance account found. Please create account 141101 first."))

        # Find default cash/bank journal
        journal = self.env["account.journal"].search([
            ("type", "in", ["cash", "bank"]),
            ("company_id", "=", self.env.company.id)
        ], limit=1)
        
        return self.create({
            "employee_id": employee_id,
            "account_id": advance_account.id,
            "journal_id": journal.id if journal else False,
        })

    def action_topup_advance(self):
        """Open wizard to top-up advance"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Top-up Advance"),
            "res_model": "advance.topup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_journal_id": self.journal_id.id,
                "default_advance_box_id": self.id,
            }
        }

    def action_settle_advance(self):
        """Open wizard to settle advance (return/pay difference)"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Settle Advance"),
            "res_model": "advance.settlement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_advance_box_id": self.id,
                "default_current_balance": self.balance,
            }
        }

    def action_refill_to_base(self):
        """Open wizard to refill advance to base amount"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Refill to Base"),
            "res_model": "advance.refill.base.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_box_id": self.id,
                "default_current_balance": self.balance,
                "default_base_amount_ref": self.remember_base_amount,
                "default_currency_id": self.currency_id.id,
                "default_journal_id": self.journal_id.id,
            }
        }

    def action_view_journal_entries(self):
        """View all journal entries for this advance box"""
        self.ensure_one()
        partner = self.employee_id.user_partner_id
        if not partner:
            return {}
            
        domain = [
            ("account_id", "=", self.account_id.id),
            ("partner_id", "=", partner.id),
        ]
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entries"),
            "res_model": "account.move.line",
            "view_mode": "tree,form",
            "domain": domain,
            "context": {"search_default_posted": 1},
        }
