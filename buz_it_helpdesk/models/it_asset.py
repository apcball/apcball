from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ItAssetCategory(models.Model):
    _name = "buz.it.asset.category"
    _description = "IT Asset Category"
    _order = "sequence, name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "Asset category must be unique per company."),
    ]



class ItAssetSpecCategory(models.Model):
    _name = "buz.it.asset.spec.category"
    _description = "IT Asset Specification Category"
    _order = "sequence, name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "Specification category must be unique per company."),
    ]


class ItAssetSoftware(models.Model):
    _name = "buz.it.asset.software"
    _description = "IT Asset Software"
    _order = "name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    version = fields.Char()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _sql_constraints = [
        ("name_version_company_uniq", "unique(name, version, company_id)", "Software must be unique per company and version."),
    ]


class ItAssetSpecLine(models.Model):
    _name = "buz.it.asset.spec.line"
    _description = "IT Asset Specification"
    _order = "sequence, id"
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    asset_id = fields.Many2one(
        "buz.it.asset",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    category_id = fields.Many2one(
        "buz.it.asset.spec.category",
        string="Specification",
        required=True,
        check_company=True,
    )
    value = fields.Char(required=True)
    company_id = fields.Many2one(
        "res.company",
        related="asset_id.company_id",
        store=True,
        index=True,
    )

    _sql_constraints = [
        (
            "asset_category_uniq",
            "unique(asset_id, category_id)",
            "Each specification category can only be used once per asset.",
        ),
    ]


class ItAsset(models.Model):
    _name = "buz.it.asset"
    _description = "IT Asset"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    _order = "name desc"

    asset_type = fields.Selection(
        [
            ("computer", "Computer"),
            ("printer", "Printer"),
            ("software_license", "Software License"),
            ("email", "Email"),
            ("system_account", "System Account"),
        ],
        string="Asset Type",
        default="computer",
        required=True,
        tracking=True,
    )
    name = fields.Char(string="Asset Number", required=True, copy=False, readonly=True, default="New", index=True)
    asset_name = fields.Char(string="Asset Name", tracking=True)
    category_id = fields.Many2one("buz.it.asset.category", string="Equipment Type", tracking=True, check_company=True)
    brand = fields.Char(tracking=True)
    model_name = fields.Char(string="Series", tracking=True)
    model_code = fields.Char(string="Model", tracking=True)
    serial_number = fields.Char(string="Serial Number", index=True, tracking=True)
    password = fields.Char(
        string="Password",
        copy=False,
        groups="buz_it_helpdesk.group_it_helpdesk_manager",
    )
    license_product = fields.Char(string="Licensed Product", tracking=True)
    license_version = fields.Char(string="License Version", tracking=True)
    license_key = fields.Char(
        string="License Key",
        copy=False,
        groups="buz_it_helpdesk.group_it_asset_manager",
    )
    license_start_date = fields.Date(string="License Start", tracking=True)
    license_expiry_date = fields.Date(string="License Expiry", tracking=True)
    license_seats = fields.Integer(string="License Seats", default=1, tracking=True)
    service_name = fields.Char(string="Platform / Service", tracking=True)
    account_username = fields.Char(string="Account Username", tracking=True)
    account_email = fields.Char(string="Account Email", tracking=True)
    account_url = fields.Char(string="Account URL", tracking=True)
    spec_line_ids = fields.One2many(
        "buz.it.asset.spec.line",
        "asset_id",
        string="Computer Specifications",
        copy=True,
    )
    software_ids = fields.Many2many("buz.it.asset.software", relation="buz_it_asset_software_rel", column1="asset_id", column2="software_id", string="Installed Software", check_company=True)
    department_id = fields.Many2one("hr.department", string="Department", tracking=True, check_company=True)
    employee_id = fields.Many2one("hr.employee", string="End User", tracking=True, check_company=True)
    custodian_id = fields.Many2one("hr.employee", string="IT Custodian", tracking=True, check_company=True)
    assigned_user_id = fields.Many2one("res.users", string="Responsible User", tracking=True)
    user_nickname = fields.Char(string="Nickname", tracking=True)
    computer_username = fields.Char(string="User Name", tracking=True)
    location = fields.Char(string="Location", tracking=True)
    status = fields.Selection(
        [
            ("available", "Available"),
            ("in_use", "In Use"),
            ("repair", "Under Repair"),
            ("lost", "Lost"),
            ("retired", "Retired"),
        ],
        string="Usage Status",
        default="available",
        required=True,
        tracking=True,
    )
    purchase_date = fields.Date(tracking=True)
    warranty_expiry_date = fields.Date(string="Warranty Expiry", tracking=True)
    vendor_id = fields.Many2one("res.partner", string="Vendor", tracking=True, check_company=True)
    repair_vendor_id = fields.Many2one("res.partner", string="Repair Vendor", tracking=True, check_company=True)
    repair_sent_date = fields.Date(string="Repair Sent Date", tracking=True)
    repair_received_date = fields.Date(string="Repair Received Date", tracking=True)
    repair_cost = fields.Monetary(string="Repair Cost", tracking=True, currency_field="company_currency_id")
    repair_symptoms = fields.Text(string="Repair Symptoms")
    repair_result = fields.Text(string="Repair Result")
    repair_ticket_id = fields.Many2one("it.helpdesk.ticket", string="Repair Ticket", tracking=True, check_company=True)
    repair_attachment_ids = fields.Many2many(
        "ir.attachment",
        "buz_it_asset_repair_attachment_rel",
        "asset_id",
        "attachment_id",
        string="Repair Evidence",
        copy=False,
    )
    company_currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    image_1920 = fields.Image(string="Asset Image", max_width=1920, max_height=1920)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "buz_it_asset_attachment_rel",
        "asset_id",
        "attachment_id",
        string="Files and Images",
        copy=False,
    )
    notes = fields.Text(string="Note")
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, index=True, default=lambda self: self.env.company)
    history_ids = fields.One2many("buz.it.asset.log", "asset_id", string="History", readonly=True)
    license_allocation_ids = fields.One2many("buz.it.asset.license.allocation", "asset_id", string="License Allocations")

    _sql_constraints = [
        ("asset_name_uniq", "unique(name)", "Asset number must be unique."),
        ("serial_company_uniq", "unique(serial_number, company_id)", "Serial Number must be unique per company."),
    ]


    @api.constrains(
        "asset_type", "asset_name", "license_product", "license_version",
        "license_start_date", "license_expiry_date", "license_seats",
        "company_id", "active",
    )
    def _check_phase_5b_master_data(self):
        for asset in self:
            if asset.asset_type in ("computer", "printer") and not asset.asset_name:
                raise ValidationError("Hardware Asset Name is required.")
            if asset.asset_type != "software_license":
                continue
            required = {
                "Licensed Product": asset.license_product,
                "License Version": asset.license_version,
                "License Start": asset.license_start_date,
                "License Expiry": asset.license_expiry_date,
            }
            missing = [label for label, value in required.items() if not value]
            if missing:
                raise ValidationError("Software License requires: %s." % ", ".join(missing))
            if asset.license_seats < 1:
                raise ValidationError("License Seats must be at least 1.")
            if asset.license_expiry_date < asset.license_start_date:
                raise ValidationError("License Expiry cannot be before License Start.")
            duplicate = self.search([
                ("id", "!=", asset.id), ("active", "=", True),
                ("company_id", "=", asset.company_id.id),
                ("asset_type", "=", "software_license"),
                ("license_product", "=", asset.license_product),
                ("license_version", "=", asset.license_version),
                ("license_start_date", "=", asset.license_start_date),
            ], limit=1)
            if duplicate:
                raise ValidationError("Duplicate Software License record for the same product, version, and start date.")
    def unlink(self):
        raise UserError("IT Assets are archived instead of deleted.")

    def _history_values(self):
        self.ensure_one()
        return {
            "asset_id": self.id,
            "performed_by_id": self.env.user.id,
            "employee_id": self.employee_id.id,
            "custodian_id": self.custodian_id.id,
            "assigned_user_id": self.assigned_user_id.id,
            "department_id": self.department_id.id,
            "location": self.location,
            "status": self.status,
        }

    def _create_history(self, event_type, old_value=False, new_value=False, **extra):
        self.ensure_one()
        values = self._history_values()
        values.update({
            "event_type": event_type,
            "event_date": fields.Datetime.now(),
            "old_value": old_value or False,
            "new_value": new_value or False,
        })
        values.update(extra)
        return self.env["buz.it.asset.log"].sudo().create(values)

    def _ensure_assignable(self):
        for asset in self:
            if asset.status in ("repair", "lost", "retired"):
                raise ValidationError("An asset in Repair, Lost, or Retired status cannot be assigned.")
            if asset.asset_type == "software_license" and asset.license_expiry_date and asset.license_expiry_date < fields.Date.context_today(asset):
                raise ValidationError("An expired Software License cannot be assigned.")

    def action_assign(self, employee_id=False, custodian_id=False, assigned_user_id=False):
        self._ensure_assignable()
        for asset in self:
            employee = self.env["hr.employee"].browse(employee_id) if employee_id else asset.employee_id
            user_id = assigned_user_id or (employee.user_id.id if employee and employee.user_id else asset.assigned_user_id.id)
            asset.with_context(skip_asset_history=True).write({
                "employee_id": employee.id if employee else False,
                "custodian_id": custodian_id or asset.custodian_id.id or False,
                "assigned_user_id": user_id or False,
                "status": "in_use",
            })
            asset._create_history("assign", new_value="Assigned")
        return True

    def action_return(self):
        for asset in self:
            if asset.status in ("repair", "lost", "retired"):
                raise ValidationError("Only an assigned active asset can be returned.")
            asset.with_context(skip_status_sync=True, skip_asset_history=True).write({
                "employee_id": False,
                "assigned_user_id": False,
                "status": "available",
            })
            asset._create_history("return", new_value="Returned")
        return True

    def action_send_to_repair(self, repair_vendor_id=False, repair_sent_date=False, repair_cost=0.0, repair_symptoms=False, ticket_id=False, repair_attachment_ids=False):
        for asset in self:
            if asset.status in ("retired", "lost"):
                raise ValidationError("Retired or Lost assets cannot be sent to repair.")
            asset.with_context(skip_status_sync=True, skip_asset_history=True).write({"status": "repair", "employee_id": False, "assigned_user_id": False})
            asset._create_history(
                "repair_send",
                ticket_id=ticket_id or asset.repair_ticket_id.id or False,
                repair_vendor_id=repair_vendor_id or asset.repair_vendor_id.id or False,
                repair_sent_date=repair_sent_date or asset.repair_sent_date or fields.Date.context_today(asset),
                repair_cost=repair_cost or asset.repair_cost or 0.0,
                repair_symptoms=repair_symptoms or asset.repair_symptoms or False,
                evidence_attachment_ids=repair_attachment_ids or [fields.Command.set(asset.repair_attachment_ids.ids)],
            )
        return True

    def action_repair_done(self, repair_received_date=False, repair_result=False, ticket_id=False):
        for asset in self:
            if asset.status != "repair":
                raise ValidationError("Only an asset under repair can be marked Repair Done.")
            asset.with_context(skip_asset_history=True).write({"status": "available"})
            asset._create_history(
                "repair_done",
                ticket_id=ticket_id or asset.repair_ticket_id.id or False,
                repair_received_date=repair_received_date or asset.repair_received_date or fields.Date.context_today(asset),
                repair_result=repair_result or asset.repair_result or False,
            )
        return True

    def action_mark_lost(self, ticket_id=False):
        for asset in self:
            if asset.status == "retired":
                raise ValidationError("A Retired asset cannot be marked Lost.")
            asset.with_context(skip_status_sync=True, skip_asset_history=True).write({"status": "lost", "employee_id": False, "assigned_user_id": False})
            asset._create_history("lost", ticket_id=ticket_id or asset.repair_ticket_id.id or False, new_value="Lost")
        return True

    def action_recover(self, ticket_id=False):
        for asset in self:
            if asset.status != "lost":
                raise ValidationError("Only a Lost asset can be recovered.")
            asset.with_context(skip_asset_history=True).write({"status": "available"})
            asset._create_history("recover", ticket_id=ticket_id or asset.repair_ticket_id.id or False, new_value="Recovered")
        return True

    def action_retire(self, ticket_id=False):
        for asset in self:
            if asset.status == "retired":
                continue
            asset.with_context(skip_status_sync=True, skip_asset_history=True).write({
                "assigned_user_id": False,
                "employee_id": False,
                "custodian_id": False,
                "status": "retired",
                "active": False,
            })
            asset._create_history("retire", ticket_id=ticket_id or asset.repair_ticket_id.id or False, new_value="Retired")
        return True

    def action_set_under_repair(self):
        return self.action_send_to_repair()

    def action_set_damaged(self):
        return self.action_mark_lost()

    def action_set_retired(self):
        return self.action_retire()
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("buz.it.asset") or "New"
            if vals.get("assigned_user_id") or vals.get("employee_id"):
                vals["status"] = "in_use"
            else:
                vals["status"] = "available"
        return super().create(vals_list)

    def write(self, vals):
        tracked_fields = {"employee_id", "custodian_id", "assigned_user_id", "department_id", "location", "status"}
        before = {
            asset.id: {field: asset[field] for field in tracked_fields if field in vals}
            for asset in self
        }
        if (vals.get("assigned_user_id") or vals.get("employee_id") or vals.get("custodian_id")) and not self.env.context.get("skip_assignment_guard"):
            self._ensure_assignable()
        if ("assigned_user_id" in vals or "employee_id" in vals) and not self.env.context.get("skip_status_sync"):
            vals = dict(vals)
            if vals.get("assigned_user_id") or vals.get("employee_id"):
                vals["status"] = "in_use"
            else:
                vals["status"] = "available"
        result = super().write(vals)
        if not self.env.context.get("skip_asset_history"):
            for asset in self:
                changed = []
                for field, old_value in before.get(asset.id, {}).items():
                    new_value = asset[field]
                    if old_value != new_value:
                        changed.append("%s: %s -> %s" % (field, old_value, new_value))
                if changed:
                    asset._create_history("status", old_value="; ".join(changed), new_value="Updated")
        return result
    @api.onchange("assigned_user_id", "employee_id")
    def _onchange_assigned_user_id(self):
        for asset in self:
            if (asset.assigned_user_id or asset.employee_id) and asset.status == "available":
                asset.status = "in_use"
            elif not asset.assigned_user_id and not asset.employee_id:
                asset.status = "available"

    @api.constrains("asset_type", "asset_name")
    def _check_asset_name(self):
        for asset in self:
            if asset.asset_type != "printer" and not asset.asset_name:
                raise ValidationError("Asset Name is required for non-printer assets.")

    @api.constrains("status", "assigned_user_id")
    def _check_status_assignment(self):
        for asset in self:
            if asset.status == "in_use" and not (asset.assigned_user_id or asset.employee_id):
                raise ValidationError("An In Use asset must have a Current User or End User.")
            if asset.status in ("available", "retired") and (asset.assigned_user_id or asset.employee_id):
                raise ValidationError("Available and Retired assets cannot have a Current User or End User.")

    @api.constrains("purchase_date", "warranty_expiry_date")
    def _check_warranty_date(self):
        for asset in self:
            if asset.purchase_date and asset.warranty_expiry_date and asset.warranty_expiry_date < asset.purchase_date:
                raise ValidationError("Warranty Expiry cannot be before Purchase Date.")
