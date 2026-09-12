from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class IssueCategory(models.Model):
    _name = 'buz.it.category'
    _description = 'IT Issue Category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    icon = fields.Selection([
        ('keyboard-o', 'Keyboard'), ('mouse-pointer', 'Mouse'),
        ('link', 'Cable'), ('desktop', 'Monitor'), ('plug', 'Adapter'),
        ('cube', 'Other'),
    ], default='cube', required=True)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    it_issue_enabled = fields.Boolean(string='Show in IT Issue', tracking=False)
    it_category_id = fields.Many2one('buz.it.category', string='IT Issue Category')

    @api.constrains('it_issue_enabled', 'detailed_type', 'it_category_id')
    def _check_it_product(self):
        for product in self:
            if product.it_issue_enabled and (
                product.detailed_type != 'product' or not product.it_category_id
            ):
                raise ValidationError(_('IT equipment must be a storable product with an IT category.'))


class IssueConfig(models.Model):
    _name = 'buz.it.config'
    _description = 'IT Issue Company Settings'
    _check_company_auto = True
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company, ondelete='cascade')
    warehouse_id = fields.Many2one('stock.warehouse', required=True, check_company=True)
    location_id = fields.Many2one('stock.location', required=True, check_company=True,
                                 domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]")
    destination_id = fields.Many2one('stock.location', check_company=True,
                                    domain="[('usage', '=', 'inventory'), ('scrap_location', '=', False), ('company_id', '=', company_id)]")
    picking_type_id = fields.Many2one('stock.picking.type', check_company=True)
    accounting_reviewed = fields.Boolean(string='Consumption accounts reviewed / ready to use')

    _sql_constraints = [('company_unique', 'unique(company_id)', 'Only one IT configuration per company is allowed.')]

    @api.constrains('warehouse_id', 'location_id', 'destination_id', 'picking_type_id')
    def _check_locations(self):
        for config in self:
            if config.location_id.usage != 'internal' or config.location_id.company_id != config.company_id:
                raise ValidationError(_('Select an internal source location belonging to this company.'))
            if not self.env['stock.location'].search_count([
                ('id', '=', config.location_id.id), ('id', 'child_of', config.warehouse_id.view_location_id.id),
            ]):
                raise ValidationError(_('Source location must belong to the selected warehouse.'))
            if config.destination_id and (
                config.destination_id.usage != 'inventory' or config.destination_id.scrap_location
                or config.destination_id.company_id != config.company_id
            ):
                raise ValidationError(_('Choose a dedicated consumption location, not Scrap.'))
            if config.picking_type_id and (
                config.picking_type_id.company_id != config.company_id
                or config.picking_type_id.warehouse_id != config.warehouse_id
                or config.picking_type_id.code != 'outgoing'
            ):
                raise ValidationError(_('Choose a delivery operation type in the selected warehouse.'))

    def action_prepare_locations(self):
        self.ensure_one()
        if not self.env.user.has_group('buz_it_stock_mobile.group_it_manager'):
            raise AccessError(_('Only IT managers can configure consumption.'))
        self.check_access_rights('write')
        self.check_access_rule('write')
        if not self.destination_id:
            self.destination_id = self.env['stock.location'].create({
                'name': 'เบิกใช้อุปกรณ์ IT', 'usage': 'inventory',
                'company_id': self.company_id.id, 'scrap_location': False,
            })
        if not self.picking_type_id:
            self.picking_type_id = self.env['stock.picking.type'].create({
                'name': 'IT Consumption', 'code': 'outgoing', 'sequence_code': 'IT-OUT',
                'warehouse_id': self.warehouse_id.id, 'company_id': self.company_id.id,
                'default_location_src_id': self.location_id.id,
                'default_location_dest_id': self.destination_id.id,
                'use_existing_lots': True, 'use_create_lots': False,
                'create_backorder': 'never', 'reservation_method': 'manual',
            })
        return True

    def _ready(self):
        self.ensure_one()
        self._check_locations()
        if not self.destination_id or not self.picking_type_id or not self.accounting_reviewed:
            raise ValidationError(_('Please complete IT warehouse settings and review consumption accounts first.'))
        if not self.picking_type_id.active:
            raise ValidationError(_('The IT operation type is archived.'))
