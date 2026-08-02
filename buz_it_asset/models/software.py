from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ITSoftwareProduct(models.Model):
    _name = 'buz.it.software.product'
    _description = 'IT Software Product'
    _order = 'name'

    name = fields.Char(required=True)
    software_type = fields.Selection([
        ('operating_system', 'Operating System'),
        ('office', 'Office'),
        ('specialized', 'Specialized Software'),
        ('other', 'Other'),
    ], required=True, default='other')
    version = fields.Char()
    manufacturer = fields.Char()
    edition = fields.Char()
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [
        ('name_version_edition_company_uniq',
         'unique(name, version, edition, company_id)',
         'The software product must be unique per company, version, and edition.'),
    ]


class ITSoftwareLicense(models.Model):
    _name = 'buz.it.software.license'
    _description = 'IT Software License'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'expiration_date, name'

    name = fields.Char(required=True, tracking=True)
    product_id = fields.Many2one(
        'buz.it.software.product', required=True, ondelete='restrict',
        check_company=True,
    )
    license_type = fields.Selection([
        ('perpetual', 'Lifetime / Perpetual'),
        ('subscription', 'Subscription'),
        ('free', 'Free'),
        ('oem', 'OEM'),
        ('trial', 'Trial'),
    ], required=True, default='subscription')
    license_key = fields.Char(
        groups='buz_it_helpdesk.group_it_support_agent,buz_it_helpdesk.group_it_helpdesk_manager',
    )
    seat_count = fields.Integer(required=True, default=1)
    start_date = fields.Date()
    expiration_date = fields.Date()
    vendor_id = fields.Many2one('res.partner', check_company=True)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True,
        readonly=True,
    )
    cost = fields.Monetary(
        currency_field='currency_id',
        groups='buz_it_helpdesk.group_it_support_agent,buz_it_helpdesk.group_it_helpdesk_manager',
    )
    purchase_document_no = fields.Char(
        groups='buz_it_helpdesk.group_it_support_agent,buz_it_helpdesk.group_it_helpdesk_manager',
    )
    purchase_document_file = fields.Binary(
        attachment=True,
        groups='buz_it_helpdesk.group_it_support_agent,buz_it_helpdesk.group_it_helpdesk_manager',
    )
    purchase_document_filename = fields.Char(
        groups='buz_it_helpdesk.group_it_support_agent,buz_it_helpdesk.group_it_helpdesk_manager',
    )
    responsible_employee_id = fields.Many2one(
        'hr.employee', check_company=True,
    )
    responsible_department_id = fields.Many2one(
        'hr.department', check_company=True,
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True,
    )
    installation_ids = fields.One2many(
        'buz.it.software.installation', 'license_id', readonly=True,
    )
    active_installation_count = fields.Integer(
        compute='_compute_active_installation_count',
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    @api.depends('installation_ids.active')
    def _compute_active_installation_count(self):
        for record in self:
            record.active_installation_count = len(
                record.installation_ids.filtered('active'))

    @api.constrains('seat_count', 'license_type')
    def _check_seat_count(self):
        if any(record.license_type != 'free' and record.seat_count < 1
               for record in self):
            raise ValidationError(_('License seats must be at least one.'))

    @api.constrains('start_date', 'expiration_date')
    def _check_contract_dates(self):
        for record in self:
            if (record.start_date and record.expiration_date
                    and record.expiration_date < record.start_date):
                raise ValidationError(_('The expiration date cannot be before the start date.'))


class ITSoftwareInstallation(models.Model):
    _name = 'buz.it.software.installation'
    _description = 'IT Software Installation'
    _check_company_auto = True
    _order = 'install_date desc, id desc'

    license_id = fields.Many2one(
        'buz.it.software.license', required=True, ondelete='restrict',
        check_company=True, index=True,
    )
    asset_id = fields.Many2one('buz.it.asset', ondelete='restrict', check_company=True)
    employee_id = fields.Many2one('hr.employee', ondelete='restrict', check_company=True)
    install_date = fields.Date(required=True, default=fields.Date.context_today)
    uninstall_date = fields.Date(readonly=True)
    installed_by_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user, readonly=True,
    )
    uninstalled_by_id = fields.Many2one('res.users', readonly=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        readonly=True, index=True,
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    @api.constrains('asset_id', 'employee_id')
    def _check_single_target(self):
        for record in self:
            if bool(record.asset_id) == bool(record.employee_id):
                raise ValidationError(_('Installation must target exactly one hardware asset or employee.'))

    @api.constrains('company_id', 'license_id', 'asset_id', 'employee_id')
    def _check_companies(self):
        for record in self:
            links = (
                record.license_id, record.asset_id, record.employee_id,
                record.license_id.responsible_employee_id,
                record.license_id.responsible_department_id,
            )
            if any(link and link.company_id and link.company_id != record.company_id
                   for link in links):
                raise ValidationError(_('All installation records must belong to the same company.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if bool(vals.get('asset_id')) == bool(vals.get('employee_id')):
                raise ValidationError(_(
                    'Installation must target exactly one hardware asset or employee.'
                ))
        records = super().create(vals_list)
        for record in records:
            record.action_install()
        return records

    def action_install(self):
        for record in self:
            if not record.active:
                raise UserError(_('An inactive installation cannot be installed.'))
            if record.license_id.expiration_date and record.license_id.expiration_date < fields.Date.context_today(record):
                raise UserError(_('This software license has expired.'))
            if (record.license_id.license_type != 'free'
                    and record.license_id.active_installation_count > record.license_id.seat_count):
                raise UserError(_('The software license has no available seats.'))
        return True

    def action_uninstall(self):
        for record in self:
            if not record.active:
                raise UserError(_('This installation has already been uninstalled.'))
            record.write({
                'active': False,
                'uninstall_date': fields.Date.context_today(self),
                'uninstalled_by_id': self.env.user.id,
            })
        return True

    def unlink(self):
        raise UserError(_('Installation history cannot be deleted.'))
