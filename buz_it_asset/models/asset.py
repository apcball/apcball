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
    category_id = fields.Many2one(
        'buz.it.asset.category', required=True, ondelete='restrict',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    asset_ids = fields.One2many('buz.it.asset', 'type_id', string='Hardware')

    _sql_constraints = [
        ('name_category_uniq', 'unique(name, category_id)',
         'The type name must be unique within its category.'),
    ]

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
    type_id = fields.Many2one(
        'buz.it.asset.type', ondelete='restrict',
        tracking=True,
    )
    category_id = fields.Many2one(
        'buz.it.asset.category', related='type_id.category_id', store=True,
        readonly=True, string='Category', tracking=True,
    )
    manufacturer = fields.Char()
    model = fields.Char()
    serial_number = fields.Char(tracking=True)
    purchase_date = fields.Date()
    vendor_id = fields.Many2one('res.partner', check_company=True)
    warranty_end = fields.Date()
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
    assignment_ids = fields.One2many(
        'buz.it.asset.assignment', 'asset_id', string='Assignment History',
        readonly=True,
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
                    'assigned_employee_id')
    def _check_company_links(self):
        for record in self:
            if not record.type_id:
                raise ValidationError(_('Select a hardware type.'))
            if record.type_id and not record.type_id.active:
                raise ValidationError(_('Hardware must use an active hardware type.'))
            for field_name in ('location_id', 'assigned_employee_id'):
                linked = record[field_name]
                if linked and linked.company_id and linked.company_id != record.company_id:
                    raise ValidationError(_('Related record must belong to the asset company.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('type_id'):
                raise ValidationError(_('Select a hardware type.'))
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
                    sequence_date,
                ) or 'New'
        return super().create(vals_list)

    def write(self, vals):
        if 'type_id' in vals and not vals['type_id']:
            raise ValidationError(_('Select a hardware type.'))
        return super().write(vals)

    def action_assign(self, employee_id=None):
        for asset in self:
            if asset.state != 'available':
                raise UserError(_('Only available assets can be assigned.'))
            employee = self.env['hr.employee'].browse(
                employee_id or asset.assigned_employee_id.id).exists()
            if not employee:
                raise UserError(_('Select a current holder before assigning the asset.'))
            if employee.company_id and employee.company_id != asset.company_id:
                raise ValidationError(_('The employee must belong to the asset company.'))
            self.env['buz.it.asset.assignment'].create({
                'asset_id': asset.id,
                'employee_id': employee.id,
                'assigned_date': fields.Date.context_today(self),
                'assigned_by_id': self.env.user.id,
                'company_id': asset.company_id.id,
                'location_id': asset.location_id.id,
            })
            asset.write({'assigned_employee_id': employee.id, 'state': 'assigned'})
        return True

    def action_return(self):
        for asset in self:
            if asset.state != 'assigned' or not asset.assigned_employee_id:
                raise UserError(_('Only assigned assets can be returned.'))
            open_assignment = asset.assignment_ids.filtered(
                lambda line: not line.returned_date)[:1]
            if not open_assignment:
                raise UserError(_('No open assignment exists for this asset.'))
            open_assignment.write({
                'returned_date': fields.Date.context_today(self),
                'returned_by_id': self.env.user.id,
            })
            asset.write({'assigned_employee_id': False, 'state': 'available'})
        return True

    def unlink(self):
        if any(asset.assignment_ids for asset in self):
            raise UserError(_('Assets with assignment history must be archived.'))
        return super().unlink()
