from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ItAssetLog(models.Model):
    _name = "buz.it.asset.log"
    _description = "IT Asset History"
    _order = "event_date desc, id desc"
    _check_company_auto = True

    asset_id = fields.Many2one("buz.it.asset", required=True, ondelete="restrict", index=True, check_company=True)
    company_id = fields.Many2one("res.company", related="asset_id.company_id", store=True, index=True)
    event_type = fields.Selection([
        ("assign", "Assigned"),
        ("return", "Returned"),
        ("status", "Status Changed"),
        ("repair_send", "Sent to Repair"),
        ("repair_done", "Repair Done"),
        ("lost", "Marked Lost"),
        ("recover", "Recovered"),
        ("retire", "Retired"),
        ("license_allocate", "License Allocated"),
        ("license_release", "License Released"),
        ("renewal_start", "Renewal Started"),
        ("renewal_renewed", "Renewed"),
        ("renewal_expired", "Renewal Expired"),
        ("renewal_cancelled", "Renewal Cancelled"),
    ], required=True, readonly=True)
    event_date = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
    performed_by_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", readonly=True, check_company=True)
    custodian_id = fields.Many2one("hr.employee", readonly=True, check_company=True)
    assigned_user_id = fields.Many2one("res.users", readonly=True)
    department_id = fields.Many2one("hr.department", readonly=True, check_company=True)
    location = fields.Char(readonly=True)
    status = fields.Selection([
        ("available", "Available"),
        ("in_use", "In Use"),
        ("repair", "Under Repair"),
        ("lost", "Lost"),
        ("retired", "Retired"),
    ], readonly=True)
    old_value = fields.Text(readonly=True)
    new_value = fields.Text(readonly=True)
    ticket_id = fields.Many2one("it.helpdesk.ticket", readonly=True, check_company=True)
    repair_sent_date = fields.Date(readonly=True)
    repair_received_date = fields.Date(readonly=True)
    repair_cost = fields.Monetary(readonly=True, currency_field="currency_id")
    repair_symptoms = fields.Text(readonly=True)
    repair_result = fields.Text(readonly=True)
    evidence_attachment_ids = fields.Many2many("ir.attachment", readonly=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    renewal_id = fields.Many2one("buz.it.asset.renewal", readonly=True, ondelete="restrict")

    def write(self, vals):
        raise UserError("IT Asset History is immutable.")

    def unlink(self):
        raise UserError("IT Asset History cannot be deleted.")


class ItAssetLicenseAllocation(models.Model):
    _name = "buz.it.asset.license.allocation"
    _description = "IT Asset License Allocation"
    _check_company_auto = True
    _order = "id desc"

    asset_id = fields.Many2one("buz.it.asset", required=True, ondelete="restrict", check_company=True)
    company_id = fields.Many2one("res.company", related="asset_id.company_id", store=True, index=True)
    employee_id = fields.Many2one("hr.employee", required=True, check_company=True)
    user_id = fields.Many2one("res.users", related="employee_id.user_id", readonly=True)
    seats = fields.Integer(required=True, default=1)
    active = fields.Boolean(default=True)
    allocated_date = fields.Date(required=True, default=fields.Date.context_today)
    returned_date = fields.Date()

    @api.constrains("asset_id", "employee_id", "seats", "active")
    def _check_allocation(self):
        for allocation in self:
            if allocation.asset_id.asset_type != "software_license":
                raise ValidationError("License allocation is only available for Software License assets.")
            if allocation.seats < 1:
                raise ValidationError("Allocated seats must be at least 1.")
            if allocation.asset_id.license_expiry_date and allocation.asset_id.license_expiry_date < fields.Date.context_today(self):
                raise ValidationError("Expired Software License cannot be allocated.")
            allocated = sum(self.search([
                ("id", "!=", allocation.id),
                ("asset_id", "=", allocation.asset_id.id),
                ("active", "=", True),
            ]).mapped("seats")) + (allocation.seats if allocation.active else 0)
            if allocated > allocation.asset_id.license_seats:
                raise ValidationError("License allocation cannot exceed the available seats.")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.asset_id._create_history("license_allocate", new_value="%s seat(s)" % record.seats)
        return records

    def write(self, vals):
        if set(vals) - {"active", "returned_date"}:
            raise UserError("License allocation details are immutable; return and archive the allocation instead.")
        result = super().write(vals)
        for record in self:
            if vals.get("active") is False:
                record.asset_id._create_history("license_release", old_value="%s seat(s)" % record.seats)
        return result

    def unlink(self):
        raise UserError("License allocations are archived instead of deleted.")
