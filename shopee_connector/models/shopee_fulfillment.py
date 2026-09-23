import base64
import io
import json
import logging
import zipfile
from datetime import timedelta

from odoo import api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.modules.registry import Registry

from .shopee_api import ShopeeAPIError
from .shopee_shipping_helpers import (
    document_result, order_detail, response,
    shipment_already_arranged, shipping_choices, validate_choice,
)

_logger = logging.getLogger(__name__)
MANAGER = 'sales_team.group_sale_manager'


class ShippingPending(Exception):
    """A read-only prerequisite is still being prepared by Shopee."""


def require_manager(record):
    if not record.env.user.has_group(MANAGER):
        raise AccessError('Only a Sales Manager can arrange Shopee shipments.')
    record.check_access_rights('write')
    record.check_access_rule('write')


class ShopeeFulfillmentBatch(models.Model):
    _name = 'shopee.fulfillment.batch'
    _description = 'Shopee Shipping Batch'
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: fields.Datetime.now().strftime('Shipping %Y-%m-%d %H:%M:%S'))
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    job_ids = fields.Many2many('shopee.fulfillment.job', string='Orders', check_company=True, readonly=True)
    progress = fields.Char(compute='_compute_progress')
    sender_name = fields.Char(string='Sender name for this batch')
    file_data = fields.Binary(attachment=True, readonly=True)
    file_name = fields.Char(readonly=True)
    download_note = fields.Char(readonly=True)

    @api.depends('job_ids.state')
    def _compute_progress(self):
        for batch in self:
            counts = {}
            for job in batch.job_ids:
                counts[job.state] = counts.get(job.state, 0) + 1
            batch.progress = ' | '.join(f'{key}: {count}' for key, count in sorted(counts.items()))

    def action_queue(self):
        require_manager(self)
        for batch in self:
            batch.job_ids.filtered(lambda j: j.state == 'choice').action_queue()
        return True

    def action_reload(self):
        require_manager(self)
        for batch in self:
            batch.job_ids.filtered(lambda j: j.state in ('choice', 'error', 'uncertain')).action_reload()
        return True

    def action_select_dropoff(self):
        require_manager(self)
        for batch in self:
            for job in batch.job_ids.filtered(lambda j: j.state == 'choice'):
                options = job.option_ids.filtered(lambda option: option.method == 'dropoff')
                if len(options) == 1:
                    values = {'option_id': options.id}
                    if batch.sender_name:
                        values['sender_name'] = batch.sender_name
                    job.write(values)
        return True

    def action_download(self):
        require_manager(self)
        self.ensure_one()
        ready = self.job_ids.filtered(lambda j: j.state == 'ready' and j.label_data)
        if not ready:
            raise UserError('No labels are ready. Refresh this page after the worker finishes.')
        stream = io.BytesIO()
        # Keep original carrier PDFs; include an explicit manifest for partial batches.
        import csv
        manifest_stream = io.StringIO()
        writer = csv.writer(manifest_stream)
        writer.writerow(['Order', 'Shop', 'State', 'Message'])
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for job in self.job_ids:
                writer.writerow([job.order_id.shopee_order_sn, job.config_id.name, job.state, job.message or ''])
                if job in ready:
                    archive.writestr(job.label_filename, base64.b64decode(job.label_data))
            archive.writestr('results.csv', manifest_stream.getvalue().encode('utf-8-sig'))
        self.write({
            'file_data': base64.b64encode(stream.getvalue()),
            'file_name': f'shopee_labels_{self.id}.zip',
            'download_note': f'{len(ready)} of {len(self.job_ids)} labels included. See results.csv for missing orders.',
        })
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': f'/web/content/shopee.fulfillment.batch/{self.id}/file_data/{self.file_name}?download=true'}


class ShopeeFulfillmentOption(models.Model):
    _name = 'shopee.fulfillment.option'
    _description = 'Shopee Carrier Option'
    _check_company_auto = True

    name = fields.Char(required=True)
    job_id = fields.Many2one('shopee.fulfillment.job', required=True, ondelete='cascade', check_company=True)
    company_id = fields.Many2one(related='job_id.company_id', store=True)
    method = fields.Selection([('pickup', 'Pickup'), ('dropoff', 'Drop off')], required=True)
    payload = fields.Text(required=True)


class ShopeeFulfillmentJob(models.Model):
    _name = 'shopee.fulfillment.job'
    _description = 'Shopee Shipment and Label'
    _rec_name = 'order_id'
    _order = 'id desc'
    _check_company_auto = True
    _sql_constraints = [('order_unique', 'unique(order_id)', 'A shipping job already exists for this order.')]

    order_id = fields.Many2one('sale.order', required=True, ondelete='restrict', check_company=True, readonly=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    config_id = fields.Many2one(related='order_id.shopee_config_id', store=True)
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, readonly=True)
    option_ids = fields.One2many('shopee.fulfillment.option', 'job_id', readonly=True)
    option_id = fields.Many2one('shopee.fulfillment.option', string='Pickup / dropoff option', check_company=True)
    sender_name = fields.Char(string='Sender name (if required)')
    confirm_sale = fields.Boolean(string='Confirm Odoo sale before arranging shipment', default=True)
    document_type = fields.Selection([
        ('NORMAL_AIR_WAYBILL', 'Normal airway bill'),
        ('THERMAL_AIR_WAYBILL', 'Thermal airway bill'),
    ], default='NORMAL_AIR_WAYBILL', required=True)
    state = fields.Selection([
        ('prepare', 'Loading options'), ('choice', 'Select shipping option'),
        ('queued', 'Queued for shipment'), ('uncertain', 'Check shipment result'),
        ('shipped', 'Shipment arranged'), ('document', 'Preparing label'),
        ('ready', 'Label ready'), ('error', 'Needs attention'),
    ], default='prepare', required=True, readonly=True, index=True)
    message = fields.Text(readonly=True)
    package_number = fields.Char(readonly=True)
    tracking_number = fields.Char(readonly=True)
    shipment_requested_at = fields.Datetime(readonly=True)
    arranged_at = fields.Datetime(readonly=True)
    document_requested_at = fields.Datetime(readonly=True)
    next_run = fields.Datetime(default=fields.Datetime.now, readonly=True, index=True)
    attempts = fields.Integer(readonly=True)
    label_data = fields.Binary(attachment=True, readonly=True)
    label_filename = fields.Char(readonly=True)

    @api.constrains('option_id', 'order_id')
    def _check_option(self):
        for job in self:
            if job.option_id and job.option_id.job_id != job:
                raise UserError('Choose a shipping option belonging to this order.')

    def write(self, values):
        # Readonly XML is not a server-side protection against RPC writes.
        editable = {'option_id', 'sender_name', 'document_type', 'confirm_sale'}
        if editable.intersection(values):
            require_manager(self)
            if any(j.state not in ('choice', 'error') for j in self):
                raise UserError('Reload shipping options before editing this job.')
            if 'document_type' in values and any(j.document_requested_at for j in self):
                raise UserError('The document type cannot change after a label was requested.')
        return super().write(values)

    def action_queue(self):
        require_manager(self)
        for job in self:
            if job.state != 'choice':
                continue
            if not job.option_id:
                raise UserError(f'Select a shipping option for {job.order_id.name}.')
            job.write({'state': 'queued', 'message': False, 'user_id': self.env.uid,
                       'next_run': fields.Datetime.now(), 'attempts': 0})
        self.env.ref('shopee_connector.cron_shopee_fulfillment')._trigger()
        return True

    def action_reload(self):
        require_manager(self)
        for job in self:
            if job.state not in ('choice', 'error', 'uncertain'):
                continue
            # Reload never resubmits an uncertain shipment; label work may resume.
            state = 'document' if job.document_requested_at else ('shipped' if job.arranged_at else 'prepare')
            job.write({'state': state, 'message': False, 'user_id': self.env.uid,
                       'next_run': fields.Datetime.now(), 'attempts': 0})
        self.env.ref('shopee_connector.cron_shopee_fulfillment')._trigger()
        return True

    def action_open(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        return {'type': 'ir.actions.act_window', 'name': 'Shopee Shipment',
                'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'current'}

    def action_retry_label(self):
        require_manager(self)
        for job in self:
            if not job.arranged_at or job.state != 'error':
                raise UserError('Only a failed label for an arranged shipment can be regenerated.')
            job.write({'state': 'shipped', 'document_requested_at': False,
                       'message': False, 'attempts': 0, 'next_run': fields.Datetime.now()})
        self.env.ref('shopee_connector.cron_shopee_fulfillment')._trigger()
        return True

    def _client(self):
        self.ensure_one()
        order = self.order_id
        order.check_access_rights('write')
        order.check_access_rule('write')
        config = self.config_id
        if not order.is_shopee_order or not order.shopee_order_sn or not config or not config.active:
            raise UserError('A real imported Shopee order and an active shop connection are required.')
        if config.company_id != order.company_id:
            raise UserError('Order company does not match the Shopee shop company.')
        config.check_access_rights('write')
        config.check_access_rule('write')
        return config._get_api(), config._ensure_valid_token()

    def _detail(self, client, token):
        detail, package = order_detail(client.get_order_detail(token, [self.order_id.shopee_order_sn]), self.order_id.shopee_order_sn)
        self.order_id.update_shopee_status(detail.get('order_status', ''))
        self.package_number = package.get('package_number') or False
        if detail.get('order_status') in ('CANCELLED', 'IN_CANCEL', 'UNPAID'):
            raise UserError('The Shopee order is cancelled, cancelling, or unpaid.')
        return detail, package

    def _prepare(self, client, token):
        detail, package = self._detail(client, token)
        if shipment_already_arranged(detail, package):
            self.write({'state': 'shipped', 'arranged_at': self.arranged_at or fields.Datetime.now(), 'message': False})
            return
        if self.shipment_requested_at:
            self.write({'state': 'uncertain', 'message': 'A shipment request was already attempted. Check Seller Centre; do not send it again automatically.'})
            return
        if detail.get('order_status') != 'READY_TO_SHIP':
            raise UserError('Shopee order is not READY_TO_SHIP.')
        options = shipping_choices(client.get_shipping_parameter(token, self.order_id.shopee_order_sn))
        super(ShopeeFulfillmentJob, self).write({'option_id': False})
        self.option_ids.unlink()
        for name, method, payload in options:
            self.env['shopee.fulfillment.option'].create({'job_id': self.id, 'name': name, 'method': method,
                                                       'payload': json.dumps(payload)})
        self.write({'state': 'choice', 'message': 'Choose pickup/dropoff, then queue this order.'})

    def _ship(self, client, token):
        detail, package = self._detail(client, token)
        if shipment_already_arranged(detail, package):
            self.write({'state': 'shipped', 'arranged_at': fields.Datetime.now()})
            return
        if self.shipment_requested_at:
            self.write({'state': 'uncertain', 'message': 'A shipment request was previously attempted. Check Seller Centre.'})
            return
        if detail.get('order_status') != 'READY_TO_SHIP':
            raise UserError('Shopee order is no longer ready to ship.')
        if not self.option_id or self.option_id.job_id != self:
            raise UserError('Select a valid shipping option.')
        values = validate_choice(client.get_shipping_parameter(token, self.order_id.shopee_order_sn),
                                 self.option_id.method, json.loads(self.option_id.payload), self.sender_name or '')
        order = self.order_id
        if order.state == 'cancel':
            raise UserError('The Odoo sale order is cancelled.')
        lines = order.order_line.filtered(lambda line: not line.display_type)
        if not lines or any(not line.product_id or line.product_id.default_code == 'SHOPEE_UNMAPPED' for line in lines):
            raise UserError('Map every order line to a real product before arranging shipment.')
        if self.confirm_sale and order.state in ('draft', 'sent'):
            order.action_confirm()
        if order.state not in ('sale', 'done'):
            raise UserError('Confirm the Odoo sale order before arranging shipment.')
        # This method ONLY runs inside the dedicated cron cursor. Persist an intent
        # BEFORE external side effects so crash/timeout recovery cannot replay ship_order.
        self.write({'state': 'uncertain', 'shipment_requested_at': fields.Datetime.now(),
                    'message': 'Shipment request in progress; check its result before any retry.'})
        self.env.cr.commit()
        try:
            client.ship_order(token, order.shopee_order_sn, self.package_number or None,
                              **{self.option_id.method: values})
        except ShopeeAPIError as exc:
            # A parsed business rejection is definitive; timeouts and malformed
            # responses remain uncertain and must only be reconciled.
            if exc.error not in ('network', 'non_json_response', 'invalid_response') and not str(exc.error).startswith('http_'):
                self.write({'state': 'error', 'shipment_requested_at': False, 'message': str(exc)})
                return
            raise
        self.write({'state': 'shipped', 'arranged_at': fields.Datetime.now(), 'message': False})

    def _document_order(self):
        order = {'order_sn': self.order_id.shopee_order_sn}
        if self.package_number:
            order['package_number'] = self.package_number
        return order

    def _create_label(self, client, token):
        self._detail(client, token)
        order = self._document_order()
        tracking = response(client.get_tracking_number(token, order['order_sn'], self.package_number or None)).get('tracking_number')
        if not tracking:
            raise ShippingPending('Tracking number is not ready; the worker will check again.')
        self.tracking_number = tracking
        param = document_result(client.get_shipping_document_parameter(token, order), order['order_sn'])
        allowed = param.get('selectable_shipping_document_type') or []
        if self.document_type not in allowed:
            raise UserError('Selected label format is not available for this carrier. Select a supported format and retry.')
        payload = dict(order, tracking_number=tracking, shipping_document_type=self.document_type)
        self.write({'state': 'document', 'document_requested_at': fields.Datetime.now(), 'message': False})
        self.env.cr.commit()
        document_result(client.create_shipping_document(token, payload), order['order_sn'])

    def _poll_label(self, client, token):
        order = self._document_order()
        result = document_result(client.get_shipping_document_result(token, order), order['order_sn'])
        status = result.get('status') or result.get('shipping_document_status')
        if status == 'PROCESSING':
            self.message = 'Shopee is preparing the label. The next worker run will check again.'
            return
        if status != 'READY':
            raise UserError(f'Label task returned {status or "no status"}. Check the task in Seller Centre.')
        content = client.download_shipping_document(token, order, self.document_type)
        import re
        safe_sn = re.sub(r'[^A-Za-z0-9_-]', '_', order['order_sn'])
        self.write({'state': 'ready', 'label_data': base64.b64encode(content),
                    'label_filename': f'shopee_{self.config_id.id}_{safe_sn}.pdf', 'message': False})

    def _step(self):
        require_manager(self)
        client, token = self._client()
        getattr(self, {'prepare': '_prepare', 'queued': '_ship', 'shipped': '_create_label',
                       'document': '_poll_label'}[self.state])(client, token)

    @api.model
    def cron_process(self):
        """Isolated transactions; session advisory lock survives the intent commit."""
        jobs = self.sudo().search([
            ('state', 'in', ['prepare', 'queued', 'shipped', 'document']),
            ('config_id.active', '=', True),
            ('next_run', '<=', fields.Datetime.now()),
        ], order='next_run, id', limit=5)
        for job_id in jobs.ids:
            with Registry(self.env.cr.dbname).cursor() as cr:
                cr.execute('SELECT pg_try_advisory_lock(%s, %s)', (734291, job_id))
                if not cr.fetchone()[0]:
                    continue
                try:
                    admin = api.Environment(cr, SUPERUSER_ID, {})
                    job = admin[self._name].browse(job_id).exists()
                    if not job or job.state not in ('prepare', 'queued', 'shipped', 'document'):
                        continue
                    actor = job.user_id
                    company = job.company_id
                    if not actor.active or company not in actor.company_ids:
                        job.write({'state': 'error', 'message': 'Requesting user is inactive or no longer has access to this company.'})
                        cr.commit()
                        continue
                    job = job.with_user(actor).with_company(company)
                    previous_state = job.state
                    try:
                        job._step()
                        if job.state == previous_state:
                            job.attempts += 1
                        else:
                            job.attempts = 0
                        if job.attempts >= 20:
                            job.write({'state': 'error', 'message': 'Label still pending after 20 checks. Retry later.'})
                        job.next_run = fields.Datetime.now() + timedelta(seconds=30)
                        cr.commit()
                    except ShippingPending as exc:
                        job.attempts += 1
                        job.write({'message': str(exc), 'next_run': fields.Datetime.now() + timedelta(minutes=1)})
                        if job.attempts >= 20:
                            job.write({'state': 'error', 'message': 'Tracking number still pending after 20 checks. Retry later.'})
                        cr.commit()
                    except Exception as exc:
                        # Preserve committed external intent; roll back only this phase.
                        cr.rollback()
                        admin = api.Environment(cr, SUPERUSER_ID, {})
                        job = admin[self._name].browse(job_id)
                        state = 'uncertain' if job.state == 'uncertain' else 'error'
                        job.write({'state': state, 'message': str(exc)[:2000]})
                        cr.commit()
                        _logger.exception('Shopee fulfillment job %s requires attention', job_id)
                finally:
                    cr.execute('SELECT pg_advisory_unlock(%s, %s)', (734291, job_id))
                    cr.commit()


class SaleOrderFulfillment(models.Model):
    _inherit = 'sale.order'

    def action_shopee_shipping_batch(self):
        require_manager(self)
        if not self or len(self) > 200:
            raise UserError('Select between 1 and 200 Shopee orders per batch.')
        if len(self.company_id) != 1:
            raise UserError('Create separate batches for each company.')
        if any(not o.is_shopee_order or not o.shopee_config_id or not o.shopee_order_sn for o in self):
            raise UserError('Select imported Shopee orders with shop connections only.')
        jobs = self.env['shopee.fulfillment.job']
        # Lock all orders in a stable order so concurrent batch creation cannot race.
        self.env.cr.execute('SELECT id FROM sale_order WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
        for order in self:
            job = jobs.search([('order_id', '=', order.id)], limit=1)
            jobs |= job or jobs.create({'order_id': order.id})
        batch = self.env['shopee.fulfillment.batch'].create({
            'company_id': self.company_id.id, 'job_ids': [fields.Command.set(jobs.ids)],
        })
        self.env.ref('shopee_connector.cron_shopee_fulfillment')._trigger()
        return {'type': 'ir.actions.act_window', 'name': 'Shopee Shipping Batch',
                'res_model': batch._name, 'res_id': batch.id, 'view_mode': 'form', 'target': 'current'}
