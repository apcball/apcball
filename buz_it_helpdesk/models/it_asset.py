from odoo import api, fields, models
from odoo.exceptions import ValidationError


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

    name = fields.Char(string="Asset Number", required=True, copy=False, readonly=True, default="New", index=True)
    asset_name = fields.Char(string="Computer Name", required=True, tracking=True)
    category_id = fields.Many2one("buz.it.asset.category", string="Equipment Type", required=True, tracking=True, check_company=True)
    brand = fields.Char(tracking=True)
    model_name = fields.Char(string="Series", tracking=True)
    model_code = fields.Char(string="Model", tracking=True)
    serial_number = fields.Char(string="Serial Number", index=True, tracking=True)
    password = fields.Char(string="Password", copy=False, groups="buz_it_helpdesk.group_it_helpdesk_agent,buz_it_helpdesk.group_it_helpdesk_manager")
    spec_line_ids = fields.One2many(
        "buz.it.asset.spec.line",
        "asset_id",
        string="Computer Specifications",
        copy=True,
    )
    software_ids = fields.Many2many("buz.it.asset.software", relation="buz_it_asset_software_rel", column1="asset_id", column2="software_id", string="Installed Software", check_company=True)
    assigned_user_id = fields.Many2one("res.users", string="User", tracking=True)
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

    _sql_constraints = [
        ("asset_name_uniq", "unique(name)", "Asset number must be unique."),
        ("serial_company_uniq", "unique(serial_number, company_id)", "Serial Number must be unique per company."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("buz.it.asset") or "New"
            if vals.get("assigned_user_id") and vals.get("status", "available") == "available":
                vals["status"] = "in_use"
        return super().create(vals_list)

    def write(self, vals):
        if "assigned_user_id" in vals and "status" not in vals:
            vals = dict(vals)
            if vals.get("assigned_user_id"):
                vals["status"] = "in_use"
            elif any(asset.status == "in_use" for asset in self):
                vals["status"] = "available"
        return super().write(vals)

    @api.onchange("assigned_user_id")
    def _onchange_assigned_user_id(self):
        for asset in self:
            if asset.assigned_user_id and asset.status == "available":
                asset.status = "in_use"
            elif not asset.assigned_user_id and asset.status == "in_use":
                asset.status = "available"

    @api.constrains("status", "assigned_user_id")
    def _check_status_assignment(self):
        for asset in self:
            if asset.status == "in_use" and not asset.assigned_user_id:
                raise ValidationError("An In Use asset must have a Current User.")
            if asset.status in ("available", "retired") and asset.assigned_user_id:
                raise ValidationError("Available and Retired assets cannot have a Current User.")

    @api.constrains("purchase_date", "warranty_expiry_date")
    def _check_warranty_date(self):
        for asset in self:
            if asset.purchase_date and asset.warranty_expiry_date and asset.warranty_expiry_date < asset.purchase_date:
                raise ValidationError("Warranty Expiry cannot be before Purchase Date.")
