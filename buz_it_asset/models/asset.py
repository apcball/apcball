import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ITAssetCategory(models.Model):
    _name = 'buz.it.asset.category'
    _description = 'IT Asset Category'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    type_ids = fields.One2many('buz.it.asset.type', 'category_id', string='Types')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The category name must be unique.'),
    ]

    def unlink(self):
        if any(category.type_ids for category in self):
            raise UserError(_('Categories with types must be archived.'))
        return super().unlink()


class ITAssetType(models.Model):
    _name = 'buz.it.asset.type'
    _description = 'IT Asset Type'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    asset_prefix = fields.Char(
        string='Asset Prefix', required=True, index=True, copy=False, size=16,
    )
    category_id = fields.Many2one(
        'buz.it.asset.category', required=True, ondelete='restrict',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    spec_profile = fields.Selection([
        ('generic', 'Generic'),
        ('desktop', 'Desktop PC'),
        ('laptop', 'Laptop / Notebook'),
        ('mobile', 'Tablet / Smartphone'),
        ('network', 'Network Equipment'),
        ('server', 'Server'),
        ('storage', 'Storage'),
        ('monitor', 'Monitor'),
        ('printer', 'Printer / Scanner'),
        ('ups', 'UPS'),
        ('input', 'Keyboard / Mouse'),
    ], required=True, default='generic', string='Specification Profile')
    description = fields.Text()
    asset_ids = fields.One2many('buz.it.asset', 'type_id', string='Hardware')

    _sql_constraints = [
        ('name_category_uniq', 'unique(name, category_id)',
         'The type name must be unique within its category.'),
        ('asset_prefix_uniq', 'unique(asset_prefix)',
         'The asset prefix must be unique.'),
    ]

    @api.model
    def _prefix_candidate(self, name):
        letters = re.sub(r'[^A-Z0-9]', '', (name or '').upper())
        return ('IT' + (letters[:4] or 'TYPE'))[:16]

    @api.model
    def _next_available_prefix(self, name, reserved=None):
        reserved = set(reserved or [])
        candidate = self._prefix_candidate(name)
        existing = set(self.search([]).mapped('asset_prefix')) | reserved
        if candidate not in existing:
            return candidate
        index = 2
        while True:
            suffix = str(index)
            value = candidate[:16 - len(suffix)] + suffix
            if value not in existing:
                return value
            index += 1

    @api.model_create_multi
    def create(self, vals_list):
        reserved = set()
        for vals in vals_list:
            prefix = (vals.get('asset_prefix') or '').strip().upper()
            if not prefix:
                prefix = self._next_available_prefix(vals.get('name'), reserved)
            vals['asset_prefix'] = prefix
            reserved.add(prefix)
        records = super().create(vals_list)
        for record in records:
            for company in self.env['res.company'].sudo().search([]):
                company._ensure_it_asset_sequence(record)
        return records

    def write(self, vals):
        if 'asset_prefix' in vals:
            vals['asset_prefix'] = (vals['asset_prefix'] or '').strip().upper()
        result = super().write(vals)
        if 'asset_prefix' in vals:
            for record in self:
                for company in self.env['res.company'].sudo().search([]):
                    company._ensure_it_asset_sequence(record)
        return result

    @api.constrains('asset_prefix')
    def _check_asset_prefix(self):
        for record in self:
            if not re.fullmatch(r'IT[A-Z0-9]+', record.asset_prefix or ''):
                raise ValidationError(_(
                    'Asset Prefix must start with IT and contain only uppercase '
                    'letters and numbers.'
                ))

    def unlink(self):
        if any(asset_type.asset_ids for asset_type in self):
            raise UserError(_('Types with hardware assets must be archived.'))
        return super().unlink()


class ITAssetLocation(models.Model):
    _name = 'buz.it.asset.location'
    _description = 'IT Asset Location'
    _order = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)
    description = fields.Text()

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'The location name must be unique per company.'),
    ]


class ITAsset(models.Model):
    _name = 'buz.it.asset'
    _description = 'IT Hardware Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, tracking=True)
    asset_tag = fields.Char(
        required=True, readonly=True, copy=False, default='New', tracking=True,
    )
    legacy_asset_tag = fields.Char(
        string='Legacy Asset Tag', readonly=True, copy=False, index=True,
    )
    type_id = fields.Many2one(
        'buz.it.asset.type', ondelete='restrict',
        tracking=True,
    )
    spec_profile = fields.Selection(
        related='type_id.spec_profile',
        string='Specification Profile',
        readonly=True,
    )
    category_id = fields.Many2one(
        'buz.it.asset.category', related='type_id.category_id', store=True,
        readonly=True, string='Category', tracking=True,
    )
    manufacturer = fields.Char()
    model = fields.Char()
    serial_number = fields.Char(tracking=True)
    purchase_date = fields.Date()
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True,
        readonly=True,
    )
    purchase_price = fields.Monetary(
        string='ราคาซื้อ (Purchase Price)', currency_field='currency_id',
        tracking=True,
    )
    vendor_id = fields.Many2one('res.partner', check_company=True)
    warranty_end = fields.Date()
    # Hardware specifications are intentionally free-text so the same asset
    # model can cover computers, servers, networking equipment, and peripherals.
    cpu = fields.Char(string='ซีพียู (CPU / Processor)')
    ram = fields.Char(string='แรม (RAM / Memory)')
    gpu = fields.Char(string='การ์ดจอ (GPU / Graphics)')
    motherboard = fields.Char(string='เมนบอร์ด (Motherboard)')
    storage = fields.Char(string='พื้นที่จัดเก็บ (Storage)')
    storage_type = fields.Char(string='ประเภทพื้นที่จัดเก็บ (Storage Type)')
    display = fields.Char(string='จอภาพ (Display)')
    resolution = fields.Char(string='ความละเอียด (Resolution)')
    refresh_rate = fields.Char(string='อัตรารีเฟรช (Refresh Rate)')
    operating_system = fields.Char(string='ระบบปฏิบัติการ (Operating System)')
    network = fields.Char(string='การเชื่อมต่อเครือข่าย (Network / Connectivity)')
    mac_address = fields.Char(string='ที่อยู่ MAC (MAC Address)')
    ip_address = fields.Char(string='ที่อยู่ IP (IP Address)')
    firmware = fields.Char(string='เฟิร์มแวร์ (Firmware)')
    power_supply = fields.Char(string='ไฟเลี้ยง/แบตเตอรี่ (Power Supply / Battery)')
    ports = fields.Char(string='พอร์ต/อินเทอร์เฟซ (Ports / Interfaces)')
    imei = fields.Char(string='หมายเลข IMEI (IMEI)')
    battery = fields.Char(string='แบตเตอรี่ (Battery)')
    rack_drive_details = fields.Text(string='รายละเอียดแร็ก/ไดรฟ์ (Rack / Drive Details)')
    capacity = fields.Char(string='ความจุ (Capacity)')
    interface = fields.Char(string='อินเทอร์เฟซ (Interface)')
    form_factor = fields.Char(string='ขนาดมาตรฐาน (Form Factor)')
    print_scan_type = fields.Char(string='ประเภทการพิมพ์/สแกน (Print / Scan Type)')
    runtime = fields.Char(string='ระยะเวลาสำรองไฟ (Runtime)')
    input_output = fields.Char(string='ไฟฟ้าขาเข้า/ขาออก (Input / Output)')
    connection_type = fields.Char(string='ประเภทการเชื่อมต่อ (Connection Type)')
    accessories = fields.Char(string='อุปกรณ์เสริม (Included Accessories)')
    other_specifications = fields.Text(string='สเปคอื่น ๆ (Other Specifications)')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True, tracking=True,
    )
    location_id = fields.Many2one(
        'buz.it.asset.location', check_company=True, tracking=True,
    )
    assigned_employee_id = fields.Many2one(
        'hr.employee', string='Current Holder', check_company=True,
        tracking=True,
    )
    responsible_department_id = fields.Many2one(
        'hr.department', string='Responsible Department', check_company=True,
        tracking=True,
    )
    assignment_ids = fields.One2many(
        'buz.it.asset.assignment', 'asset_id', string='Assignment History',
        readonly=True,
    )
    maintenance_ids = fields.One2many(
        'buz.it.asset.maintenance', 'asset_id', string='Maintenance History',
    )
    state = fields.Selection([
        ('available', 'Available'),
        ('assigned', 'Assigned'),
        ('repair', 'Repair'),
        ('retired', 'Retired'),
        ('lost', 'Lost'),
    ], default='available', required=True, tracking=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [
        ('asset_tag_company_uniq', 'unique(asset_tag, company_id)',
         'The asset tag must be unique per company.'),
        ('serial_company_uniq',
         'unique(company_id, serial_number)',
         'The serial number must be unique per company.'),
    ]

    @api.constrains('company_id', 'type_id', 'location_id',
                    'assigned_employee_id', 'responsible_department_id',
                    'state')
    def _check_company_links(self):
        for record in self:
            if not record.type_id:
                raise ValidationError(_('Select a hardware type.'))
            if record.type_id and not record.type_id.active:
                raise ValidationError(_('Hardware must use an active hardware type.'))
            if record.assigned_employee_id and record.responsible_department_id:
                raise ValidationError(_(
                    'Select either a current holder or a responsible department, not both.'
                ))
            if record.state == 'assigned' and not (
                    record.assigned_employee_id or record.responsible_department_id):
                raise ValidationError(_(
                    'Assigned assets must have a current holder or responsible department.'
                ))
            for field_name in (
                    'location_id', 'assigned_employee_id',
                    'responsible_department_id'):
                linked = record[field_name]
                if linked and linked.company_id and linked.company_id != record.company_id:
                    raise ValidationError(_('Related record must belong to the asset company.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('type_id'):
                raise ValidationError(_('Select a hardware type.'))
            if not vals.get('serial_number'):
                raise ValidationError(_('Enter a serial number for the asset.'))
            company = self.env['res.company'].browse(
                vals.get('company_id') or self.env.company.id,
            ).exists()
            if not company:
                raise ValidationError(_('Select a valid company.'))
            vals['company_id'] = company.id
            if vals.get('asset_tag', 'New') == 'New':
                sequence_date = self.env.context.get(
                    'ir_sequence_date', fields.Date.context_today(self),
                )
                vals['asset_tag'] = company._next_it_asset_tag(
                    self.env['buz.it.asset.type'].browse(vals['type_id']),
                    sequence_date,
                ) or 'New'
        return super().create(vals_list)

    def write(self, vals):
        if 'type_id' in vals and not vals['type_id']:
            raise ValidationError(_('Select a hardware type.'))
        if 'serial_number' in vals and not vals['serial_number']:
            raise ValidationError(_('Enter a serial number for the asset.'))
        return super().write(vals)

    def action_assign(self, employee_id=None, department_id=None):
        for asset in self:
            if asset.state != 'available':
                raise UserError(_('Only available assets can be assigned.'))
            employee = self.env['hr.employee'].browse(
                employee_id or asset.assigned_employee_id.id).exists()
            department = self.env['hr.department'].browse(
                department_id or asset.responsible_department_id.id,
            ).exists()
            if bool(employee) == bool(department):
                raise UserError(_(
                    'Select either a current holder or a responsible department before assigning.'
                ))
            if employee.company_id and employee.company_id != asset.company_id:
                raise ValidationError(_('The employee must belong to the asset company.'))
            if department.company_id and department.company_id != asset.company_id:
                raise ValidationError(_('The department must belong to the asset company.'))
            self.env['buz.it.asset.assignment'].create({
                'asset_id': asset.id,
                'employee_id': employee.id,
                'department_id': department.id,
                'assigned_date': fields.Date.context_today(self),
                'assigned_by_id': self.env.user.id,
                'company_id': asset.company_id.id,
                'location_id': asset.location_id.id,
            })
            asset.write({
                'assigned_employee_id': employee.id,
                'responsible_department_id': department.id,
                'state': 'assigned',
            })
        return True

    def action_return(self):
        for asset in self:
            if asset.state != 'assigned' or not (
                    asset.assigned_employee_id or asset.responsible_department_id):
                raise UserError(_('Only assigned assets can be returned.'))
            open_assignment = asset.assignment_ids.filtered(
                lambda line: not line.returned_date)[:1]
            if not open_assignment:
                raise UserError(_('No open assignment exists for this asset.'))
            open_assignment.write({
                'returned_date': fields.Date.context_today(self),
                'returned_by_id': self.env.user.id,
            })
            asset.write({
                'assigned_employee_id': False,
                'responsible_department_id': False,
                'state': 'available',
            })
        return True

    def unlink(self):
        if any(asset.assignment_ids for asset in self):
            raise UserError(_('Assets with assignment history must be archived.'))
        return super().unlink()
