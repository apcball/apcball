import base64
import binascii
import io
import hashlib
import math
import uuid
from collections import defaultdict

from PIL import Image

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class ITIssue(models.Model):
    _name = 'buz.it.issue'
    _description = 'IT Equipment Issue'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(default='New', readonly=True, copy=False, required=True)
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company, readonly=True)
    config_id = fields.Many2one('buz.it.config', required=True, check_company=True, readonly=True)
    employee_id = fields.Many2one('hr.employee', required=True, check_company=True)
    receiver_name = fields.Char(readonly=True)
    department_name = fields.Char(readonly=True)
    work_location_id = fields.Many2one('hr.work.location', check_company=True)
    work_location_name = fields.Char(readonly=True)
    note = fields.Text()
    state = fields.Selection([
        ('draft', 'Draft'), ('awaiting', 'Awaiting Signature'),
        ('done', 'Done'), ('cancel', 'Cancelled'),
    ], default='draft', required=True, readonly=True, tracking=True, copy=False)
    line_ids = fields.One2many('buz.it.issue.line', 'issue_id', string='Equipment', copy=True)
    signature = fields.Binary(attachment=False, readonly=True, copy=False)
    signed_on = fields.Datetime(readonly=True, copy=False)
    signed_by = fields.Char(readonly=True, copy=False)
    picking_id = fields.Many2one('stock.picking', readonly=True, copy=False, check_company=True)
    request_key = fields.Char(required=True, readonly=True, copy=False, index=True)

    _sql_constraints = [
        ('request_key_unique', 'unique(request_key)', 'This request already exists.'),
        ('picking_unique', 'unique(picking_id)', 'A picking can only belong to one IT issue.'),
    ]

    @api.model
    def _check_user(self):
        if not self.env.user.has_group('buz_it_stock_mobile.group_it_user'):
            raise AccessError(_('IT Issue access is required.'))

    def _lock(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        self.env.cr.execute('SELECT id FROM buz_it_issue WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def _check_editable(self):
        self._check_user()
        manager = self.env.user.has_group('buz_it_stock_mobile.group_it_manager')
        for issue in self:
            issue._lock()
            if issue.state in ('done', 'cancel'):
                raise UserError(_('Completed or cancelled issues cannot be changed.'))
            if issue.create_uid != self.env.user and not manager:
                raise AccessError(_('You can only modify your own issues.'))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_user()
        allowed = {'employee_id', 'work_location_id', 'note', 'line_ids', 'request_key', 'config_id', 'company_id'}
        for vals in vals_list:
            if set(vals) - allowed:
                raise AccessError(_('System fields cannot be supplied when creating an issue.'))
            config = self._get_config()
            if vals.get('company_id', self.env.company.id) != self.env.company.id or vals.get('config_id', config.id) != config.id:
                raise AccessError(_('Use the configuration of the current company.'))
            vals.update(
                company_id=self.env.company.id, config_id=config.id, state='draft', name='New',
                signature=False, signed_on=False, signed_by=False, picking_id=False,
                receiver_name=False, department_name=False, work_location_name=False,
            )
            vals['request_key'] = str(uuid.UUID(vals.get('request_key') or str(uuid.uuid4())))
        records = super().create(vals_list)
        records._check_receiver()
        return records

    def write(self, vals):
        business = {'employee_id', 'work_location_id', 'note', 'line_ids'}
        # mail.thread uses these fields when adding followers, independently of stock state.
        mail_fields = {'message_follower_ids', 'message_partner_ids', 'activity_ids'}
        if set(vals) - business - mail_fields:
            raise AccessError(_('Issue system fields can only be changed by the issue workflow.'))
        if set(vals) & business:
            self._check_editable()
        result = super().write(vals)
        if set(vals) & business:
            self._check_receiver()
            super(ITIssue, self).write({'state': 'draft'})
        return result

    def _check_receiver(self):
        for issue in self:
            employee = issue.employee_id.sudo()
            if not employee.exists() or not employee.active or employee.company_id != issue.company_id:
                raise ValidationError(_('Select an active employee in this company.'))
            if issue.work_location_id and issue.work_location_id.company_id != issue.company_id:
                raise ValidationError(_('The receiving location must belong to this company.'))

    @api.model
    def _get_config(self):
        self._check_user()
        config = self.env['buz.it.config'].search([('company_id', '=', self.env.company.id)], limit=1)
        if not config:
            raise UserError(_('Please ask an IT manager to configure the IT warehouse first.'))
        config._ready()
        return config

    def _validate_lines(self):
        self.ensure_one()
        self._check_receiver()
        self.config_id._ready()
        if not self.line_ids:
            raise ValidationError(_('Add at least one item.'))
        seen = set()
        for line in self.line_ids:
            line._validate_item()
            key = (line.product_id.id, line.lot_id.id)
            if key in seen:
                raise ValidationError(_('Duplicate product / lot. Combine its quantities into one line.'))
            seen.add(key)

    def action_submit(self):
        self._check_editable()
        for issue in self:
            issue._validate_lines()
            employee = issue.employee_id.sudo()
            vals = {
                'state': 'awaiting', 'receiver_name': employee.name,
                'department_name': employee.department_id.name or '',
                'work_location_name': issue.work_location_id.name or '',
            }
            if issue.name == 'New':
                # One sequence per company; advisory lock also covers initial setup races.
                self.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', [171700, issue.company_id.id])
                sequence = self.env['ir.sequence'].sudo().search([
                    ('code', '=', 'buz.it.issue'), ('company_id', '=', issue.company_id.id),
                ], limit=1)
                if not sequence:
                    sequence = self.env['ir.sequence'].sudo().create({
                        'name': 'IT Issue', 'code': 'buz.it.issue', 'company_id': issue.company_id.id,
                        'prefix': 'IT-ISS-%(year)s-', 'padding': 5,
                    })
                vals['name'] = sequence.next_by_id()
            super(ITIssue, issue).write(vals)
        return True

    def action_cancel(self):
        self._check_editable()
        return super().write({'state': 'cancel'})

    def action_open_app(self):
        self.ensure_one()
        self._check_user()
        self.check_access_rights('read')
        self.check_access_rule('read')
        if self.company_id != self.env.company:
            raise UserError(_('Switch to the issue company before opening this document in the app.'))
        return {
            'type': 'ir.actions.client', 'tag': 'buz_it_stock_mobile.app',
            'name': _('IT Issue'), 'params': {'issue_id': self.id},
        }

    @api.model
    def _validate_signature(self, signature):
        if not isinstance(signature, str) or len(signature) > 700000:
            raise ValidationError(_('Invalid signature image.'))
        try:
            raw = base64.b64decode(signature, validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != 'PNG' or not (50 <= image.width <= 2000 and 30 <= image.height <= 1000):
                    raise ValueError('Invalid dimensions')
                image.load()
                rgba = image.convert('RGBA')
                white = Image.new('RGBA', rgba.size, 'white')
                white.alpha_composite(rgba)
                gray = white.convert('L')
                ink = gray.point(lambda value: 255 if value < 180 else 0)
                box = ink.getbbox()
                if not box or box[2] - box[0] < 15 or box[3] - box[1] < 5 or sum(ink.histogram()[1:]) < 35:
                    raise ValueError('Blank signature')
        except (ValueError, OSError, binascii.Error, Image.DecompressionBombError) as exc:
            raise ValidationError(_('Please draw a valid signature before confirming.')) from exc
        return signature

    def action_sign(self, signature, revision):
        self.ensure_one()
        self._check_user()
        self._lock()
        if self.state == 'done':
            return self.get_detail()
        self._check_editable()
        if self.state != 'awaiting':
            raise UserError(_('Confirm the recipient and items before signing.'))
        if revision != self._revision():
            raise UserError(_('The issue or warehouse settings changed. Review the summary and sign again.'))
        self._validate_lines()
        signature = self._validate_signature(signature)
        # Any failure rolls back the picking, reservations and signature together,
        # including when this method is called by another server-side workflow.
        with self.env.cr.savepoint():
            config = self.config_id
            picking = self.env['stock.picking'].create({
                'picking_type_id': config.picking_type_id.id,
                'location_id': config.location_id.id,
                'location_dest_id': config.destination_id.id,
                'company_id': self.company_id.id, 'origin': self.name,
            })
            for line in self.line_ids.sorted(lambda row: (row.product_id.id, row.lot_id.id)):
                move = self.env['stock.move'].create({
                    'name': line.product_id.display_name, 'picking_id': picking.id,
                    'product_id': line.product_id.id, 'product_uom_qty': line.quantity,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': config.location_id.id,
                    'location_dest_id': config.destination_id.id,
                    'company_id': self.company_id.id,
                })
                move._action_confirm(merge=False)
                # Existing operation types may reserve automatically on confirm.
                # Release that selection before reserving the recipient's exact lot.
                move._do_unreserve()
                # Reserve explicitly by selected lot. Never allow _action_assign to
                # substitute a different serial or manufacture negative stock.
                available = self.env['stock.quant']._get_available_quantity(
                    line.product_id, config.location_id, lot_id=line.lot_id, strict=False,
                )
                if float_compare(available, line.quantity, precision_rounding=line.product_id.uom_id.rounding) < 0:
                    raise UserError(_('Not enough available stock: %s', line.product_id.display_name))
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', 'child_of', config.location_id.id),
                    ('company_id', '=', self.company_id.id), ('owner_id', '=', False),
                    ('lot_id', '=', line.lot_id.id),
                ])
                reserved = move._update_reserved_quantity(
                    line.quantity, config.location_id, quant_ids=quants,
                    lot_id=line.lot_id, strict=False,
                )
                if float_compare(reserved, line.quantity, precision_rounding=line.product_id.uom_id.rounding) != 0:
                    raise UserError(_('Stock was reserved by another transaction. Please review your items.'))
                if line.lot_id and any(ml.lot_id != line.lot_id for ml in move.move_line_ids):
                    raise UserError(_('The selected lot could not be reserved.'))
                # Odoo 17 move lines use quantity; reservation already supplies it.
                move.picked = True
            picking.with_context(skip_backorder=True).button_validate()
            if picking.state != 'done' or any(
                float_compare(move.quantity, move.product_uom_qty,
                              precision_rounding=move.product_uom.rounding) != 0
                for move in picking.move_ids
            ):
                raise UserError(_('Stock validation needs attention. No equipment has been issued.'))
            super(ITIssue, self).write({
                'picking_id': picking.id, 'signature': signature, 'signed_on': fields.Datetime.now(),
                'signed_by': self.receiver_name, 'state': 'done',
            })
            self.message_post(body=_('Equipment received by %s. Stock transfer %s completed.', self.receiver_name, picking.name))
        return self.get_detail()

    @api.model
    def save_request(self, payload):
        """Whitelisted mobile interface; UUID survives network retries."""
        config = self._get_config()
        key = str(uuid.UUID(payload['request_key']))
        self.env.cr.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', [key])
        issue = self.search([('request_key', '=', key)], limit=1)
        if issue:
            if issue.create_uid != self.env.user and not self.env.user.has_group('buz_it_stock_mobile.group_it_manager'):
                raise AccessError(_('This request belongs to another user.'))
            if issue.state == 'done':
                return issue.get_detail()
        lines = payload.get('lines', [])
        if not isinstance(lines, list) or len(lines) > 200:
            raise ValidationError(_('Use at most 200 equipment lines per issue.'))
        vals = {
            'employee_id': int(payload.get('employee_id') or 0),
            'work_location_id': int(payload.get('work_location_id') or 0) or False,
            'note': str(payload.get('note') or '')[:4000],
            'line_ids': [fields.Command.create({
                'product_id': int(row['product_id']), 'quantity': float(row['quantity']),
                'lot_id': int(row.get('lot_id') or 0) or False,
            }) for row in lines],
        }
        if issue:
            vals['line_ids'].insert(0, fields.Command.clear())
            issue.write(vals)
        else:
            vals.update(request_key=key, config_id=config.id)
            issue = self.create(vals)
        issue.action_submit()
        return issue.get_detail()

    @api.model
    def request_status(self, key):
        self._check_user()
        domain = [('request_key', '=', str(uuid.UUID(key))), ('company_id', '=', self.env.company.id)]
        if not self.env.user.has_group('buz_it_stock_mobile.group_it_manager'):
            domain.append(('create_uid', '=', self.env.uid))
        issue = self.search(domain, limit=1)
        return issue.get_detail() if issue else False

    def get_detail(self):
        self.ensure_one()
        self._check_user()
        self.check_access_rights('read')
        self.check_access_rule('read')
        return {
            'id': self.id, 'name': self.name, 'state': self.state, 'company_id': self.company_id.id,
            'revision': self._revision(), 'request_key': self.request_key,
            'employee_id': self.employee_id.id, 'receiver': self.receiver_name,
            'department': self.department_name or '', 'location': self.work_location_name or '',
            'work_location_id': self.work_location_id.id, 'note': self.note or '',
            'signed_on': fields.Datetime.to_string(self.signed_on) if self.signed_on else False,
            'picking_id': self.picking_id.id, 'picking_name': self.picking_id.name,
            'signature': self.signature.decode() if self.signature else False,
            'lines': [{
                'product_id': line.product_id.id, 'name': line.product_id.display_name,
                'quantity': line.quantity, 'uom': line.product_id.uom_id.name,
                'lot_id': line.lot_id.id, 'lot_name': line.lot_id.name or '',
                'tracking': line.product_id.tracking, 'rounding': line.product_id.uom_id.rounding,
            } for line in self.line_ids],
        }

    def _revision(self):
        self.ensure_one()
        config = self.config_id
        values = (self.write_date, self.employee_id.id, self.receiver_name, self.department_name,
                  self.work_location_id.id, self.work_location_name, self.note,
                  config.write_date, config.location_id.id, config.destination_id.id,
                  config.picking_type_id.id, config.accounting_reviewed,
                  [(line.id, line.product_id.id, line.quantity, line.lot_id.id, line.write_date)
                   for line in self.line_ids])
        return hashlib.sha256(repr(values).encode()).hexdigest()

    @api.model
    def get_people(self, search=''):
        self._check_user()
        # Deliberately narrow output; never return private hr.employee fields.
        employees = self.env['hr.employee'].sudo().search([
            ('company_id', '=', self.env.company.id), ('active', '=', True),
            ('name', 'ilike', str(search)[:100]),
        ], limit=30, order='name')
        return [{
            'id': emp.id, 'name': emp.name, 'department': emp.department_id.name or '',
            'location_id': emp.work_location_id.id, 'image': emp.image_128.decode() if emp.image_128 else False,
        } for emp in employees]

    @api.model
    def get_bootstrap(self):
        self._check_user()
        config = self.env['buz.it.config'].search([('company_id', '=', self.env.company.id)], limit=1)
        error = ''
        try:
            self._get_config()
        except (UserError, ValidationError) as exc:
            error = str(exc)
        return {
            'company_id': self.env.company.id, 'company': self.env.company.name,
            'user': self.env.user.name, 'user_id': self.env.uid,
            'manager': self.env.user.has_group('buz_it_stock_mobile.group_it_manager'),
            'warehouse': config.warehouse_id.name or '', 'setup_error': error,
            'categories': self.env['buz.it.category'].search_read([], ['name', 'icon']),
            'locations': self.env['hr.work.location'].sudo().search_read(
                [('company_id', '=', self.env.company.id)], ['name'], order='name'),
        }

    @api.model
    def get_catalog(self, search='', category_id=False, offset=0):
        config = self._get_config()
        domain = [('it_issue_enabled', '=', True), ('detailed_type', '=', 'product'),
                  ('company_id', 'in', [False, self.env.company.id])]
        if category_id:
            domain.append(('it_category_id', '=', int(category_id)))
        if search:
            term = str(search)[:100]
            lots = self.env['stock.lot'].search([
                ('name', 'ilike', term), ('company_id', '=', self.env.company.id),
            ], limit=200)
            domain += ['|', '|', ('name', 'ilike', term), ('default_code', 'ilike', term), ('id', 'in', lots.product_id.ids)]
        products = self.env['product.product'].search(domain, limit=41, offset=max(0, int(offset)), order='name, id')
        return {'more': len(products) > 40, 'products': [{
            'id': p.id, 'name': p.display_name, 'category_id': p.it_category_id.id,
            'category': p.it_category_id.name, 'tracking': p.tracking,
            'has_image': bool(p.image_128), 'category_icon': p.it_category_id.icon,
            'available': max(0, p.with_context(location=config.location_id.id).free_qty),
            'uom': p.uom_id.name, 'rounding': p.uom_id.rounding,
        } for p in products[:40]]}

    @api.model
    def get_lots(self, product_id):
        config = self._get_config()
        product = self.env['product.product'].browse(int(product_id)).exists()
        if not product or not product.it_issue_enabled or product.company_id not in (self.env.company, self.env['res.company']):
            raise AccessError(_('Equipment is not available in this company.'))
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id), ('location_id', 'child_of', config.location_id.id),
            ('company_id', '=', self.env.company.id), ('lot_id', '!=', False),
            ('owner_id', '=', False),
        ])
        amounts = defaultdict(float)
        for quant in quants:
            amounts[quant.lot_id] += quant.quantity - quant.reserved_quantity
        return [{'id': lot.id, 'name': lot.name, 'available': qty}
                for lot, qty in sorted(amounts.items(), key=lambda item: item[0].name) if qty > 0]

    @api.model
    def get_dashboard(self):
        config = self._get_config()
        domain = [('company_id', '=', self.env.company.id), ('config_id', '=', config.id),
                  '|', ('picking_id', '=', False), ('picking_id.location_id', '=', config.location_id.id)]
        latest = self.search(domain, limit=8)
        month = fields.Date.context_today(self).replace(day=1)
        done = self.search(domain + [('state', '=', 'done'), ('signed_on', '>=', month)])
        totals = defaultdict(float)
        categories = defaultdict(float)
        for line in done.line_ids:
            totals[line.product_id.uom_id.name] += line.quantity
            categories[(line.product_id.it_category_id.name, line.product_id.uom_id.name)] += line.quantity
        products = self.env['product.product'].search([
            ('it_issue_enabled', '=', True), ('detailed_type', '=', 'product'),
            ('company_id', 'in', [False, self.env.company.id]),
        ]).with_context(location=config.location_id.id)
        stock = defaultdict(float)
        value = 0
        manager = self.env.user.has_group('buz_it_stock_mobile.group_it_manager')
        for product in products:
            stock[product.uom_id.name] += product.qty_available
            if manager:
                value += product.qty_available * product.with_company(self.env.company).standard_price
        return {
            'recent': [{'id': issue.id, 'name': issue.name, 'receiver': issue.receiver_name,
                        'state': issue.state, 'date': fields.Datetime.to_string(issue.create_date),
                        'count': len(issue.line_ids)} for issue in latest],
            'month_count': len(done), 'totals': dict(totals), 'stock': dict(stock),
            'categories': [{'name': name, 'uom': uom, 'qty': qty} for (name, uom), qty in categories.items()],
            'product_count': len(products), 'value': value if manager else False,
            'currency': self.env.company.currency_id.symbol,
        }


class ITIssueLine(models.Model):
    _name = 'buz.it.issue.line'
    _description = 'IT Issue Equipment Line'
    _check_company_auto = True

    issue_id = fields.Many2one('buz.it.issue', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='issue_id.company_id', store=True, index=True)
    product_id = fields.Many2one('product.product', required=True, check_company=True)
    quantity = fields.Float(required=True, default=1, digits='Product Unit of Measure')
    lot_id = fields.Many2one('stock.lot', check_company=True)

    @api.model
    def _check_quantity(self, product, quantity):
        if not math.isfinite(quantity) or quantity <= 0 or not float_is_zero(
            quantity / product.uom_id.rounding - round(quantity / product.uom_id.rounding), precision_digits=6,
        ):
            raise ValidationError(_('Enter a positive quantity matching the product unit rounding.'))

    def _validate_item(self):
        for line in self:
            p = line.product_id
            if not p.active or not p.it_issue_enabled or p.detailed_type != 'product':
                raise ValidationError(_('Select an active, storable IT product.'))
            if p.company_id and p.company_id != line.company_id:
                raise ValidationError(_('Product belongs to another company.'))
            self._check_quantity(p, line.quantity)
            if p.tracking != 'none' and not line.lot_id:
                raise ValidationError(_('Select a serial / lot for %s.', p.display_name))
            if p.tracking == 'none' and line.lot_id:
                raise ValidationError(_('This product does not use serial / lot tracking.'))
            if line.lot_id and (line.lot_id.product_id != p or line.lot_id.company_id != line.company_id):
                raise ValidationError(_('The serial / lot does not match this product and company.'))
            if p.tracking == 'serial' and line.quantity != 1:
                raise ValidationError(_('Each serial number must have a quantity of one.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if set(vals) - {'issue_id', 'product_id', 'quantity', 'lot_id'}:
                raise AccessError(_('Unsupported equipment fields.'))
            self.env['buz.it.issue'].browse(vals['issue_id'])._check_editable()
            self._check_quantity(self.env['product.product'].browse(vals['product_id']), float(vals.get('quantity', 1)))
        result = super().create(vals_list)
        result._validate_item()
        super(ITIssue, result.issue_id).write({'state': 'draft'})
        return result

    def write(self, vals):
        if set(vals) - {'product_id', 'quantity', 'lot_id'}:
            raise AccessError(_('Equipment cannot be moved to a different issue.'))
        self.issue_id._check_editable()
        for line in self:
            product = self.env['product.product'].browse(vals['product_id']) if vals.get('product_id') else line.product_id
            self._check_quantity(product, float(vals.get('quantity', line.quantity)))
        result = super().write(vals)
        self._validate_item()
        super(ITIssue, self.issue_id).write({'state': 'draft'})
        return result

    def unlink(self):
        issues = self.issue_id
        issues._check_editable()
        result = super().unlink()
        super(ITIssue, issues).write({'state': 'draft'})
        return result
