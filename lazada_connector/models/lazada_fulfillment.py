import base64
import csv
import io
import logging
import re
import zipfile
from datetime import timedelta

from odoo import api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.modules.registry import Registry

from .lazada_api import LazadaAPIError
from .lazada_shipping_helpers import (
    ShippingRejected, classify_items, document, pack_result, packages, rts_result,
)

_logger = logging.getLogger(__name__)
MANAGER = 'lazada_connector.group_lazada_manager'
# Errors after which Lazada may still have applied the request.
UNCERTAIN_ERRORS = ('network', 'non_json_response', 'invalid_response')
WORKER_STATES = ('prepare', 'queued', 'packed', 'shipped')
LOCK_KEY = 734292


class ShippingPending(Exception):
    """A read-only prerequisite is still being prepared by Lazada."""


def require_manager(record):
    if not record.env.user.has_group(MANAGER):
        raise AccessError('Only a Lazada Manager can arrange Lazada shipments.')
    record.check_access_rights('write')
    record.check_access_rule('write')


def definitive(exc):
    """True when Lazada answered and rejected the request."""
    if isinstance(exc, ShippingRejected):
        return True
    if isinstance(exc, LazadaAPIError):
        return (exc.error not in UNCERTAIN_ERRORS
                and not str(exc.error).startswith('http_')
                and str(exc.error_type).upper() not in ('ISP', 'SYSTEM'))
    return False


class LazadaFulfillmentBatch(models.Model):
    _name = 'lazada.fulfillment.batch'
    _description = 'Lazada Shipping Batch'
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: fields.Datetime.now().strftime('Shipping %Y-%m-%d %H:%M:%S'))
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    job_ids = fields.Many2many('lazada.fulfillment.job', string='Orders', check_company=True, readonly=True)
    progress = fields.Char(compute='_compute_progress')
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

    def action_download(self):
        require_manager(self)
        self.ensure_one()
        ready = self.job_ids.filtered(lambda j: j.state == 'ready' and j.label_data)
        if not ready:
            raise UserError('No labels are ready. Refresh this page after the worker finishes.')
        stream = io.BytesIO()
        # Keep original carrier PDFs; include an explicit manifest for partial batches.
        manifest_stream = io.StringIO()
        writer = csv.writer(manifest_stream)
        writer.writerow(['Order', 'Seller', 'State', 'Tracking', 'Message'])
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for job in self.job_ids:
                writer.writerow([job.order_id.lazada_order_id, job.config_id.name, job.state,
                                 job.tracking_number or '', job.message or ''])
                if job in ready:
                    archive.writestr(job.label_filename, base64.b64decode(job.label_data))
            archive.writestr('results.csv', manifest_stream.getvalue().encode('utf-8-sig'))
        self.write({
            'file_data': base64.b64encode(stream.getvalue()),
            'file_name': f'lazada_labels_{self.id}.zip',
            'download_note': f'{len(ready)} of {len(self.job_ids)} labels included. See results.csv for missing orders.',
        })
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': f'/web/content/lazada.fulfillment.batch/{self.id}/file_data/{self.file_name}?download=true'}


class LazadaFulfillmentJob(models.Model):
    _name = 'lazada.fulfillment.job'
    _description = 'Lazada Shipment and Label'
    _rec_name = 'order_id'
    _order = 'id desc'
    _check_company_auto = True
    _sql_constraints = [('order_unique', 'unique(order_id)', 'A shipping job already exists for this order.')]

    order_id = fields.Many2one('sale.order', required=True, ondelete='restrict', check_company=True, readonly=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    config_id = fields.Many2one(related='order_id.lazada_config_id', store=True)
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, readonly=True)
    confirm_sale = fields.Boolean(string='Confirm Odoo sale before arranging shipment', default=True)
    state = fields.Selection([
        ('prepare', 'Loading order'), ('choice', 'Ready to queue'),
        ('queued', 'Queued for shipment'), ('uncertain', 'Check shipment result'),
        ('packed', 'Packed'), ('shipped', 'Shipment arranged'),
        ('ready', 'Label ready'), ('error', 'Needs attention'),
    ], default='prepare', required=True, readonly=True, index=True)
    message = fields.Text(readonly=True)
    package_number = fields.Char(string='Package ID(s)', readonly=True)
    tracking_number = fields.Char(readonly=True)
    shipment_provider = fields.Char(readonly=True)
    shipment_requested_at = fields.Datetime(string='Pack requested at', readonly=True)
    packed_at = fields.Datetime(readonly=True)
    rts_requested_at = fields.Datetime(string='Ready to ship requested at', readonly=True)
    arranged_at = fields.Datetime(readonly=True)
    next_run = fields.Datetime(default=fields.Datetime.now, readonly=True, index=True)
    attempts = fields.Integer(readonly=True)
    label_data = fields.Binary(attachment=True, readonly=True)
    label_filename = fields.Char(readonly=True)

    def write(self, values):
        # Readonly XML is not a server-side protection against RPC writes.
        editable = {'confirm_sale'}
        if editable.intersection(values):
            require_manager(self)
            if any(j.state not in ('choice', 'error') for j in self):
                raise UserError('Reload this order before editing the job.')
        return super().write(values)

    def action_queue(self):
        require_manager(self)
        for job in self:
            if job.state != 'choice':
                continue
            job.write({'state': 'queued', 'message': False, 'user_id': self.env.uid,
                       'next_run': fields.Datetime.now(), 'attempts': 0})
        self.env.ref('lazada_connector.cron_lazada_fulfillment')._trigger()
        return True

    def action_reload(self):
        require_manager(self)
        for job in self:
            if job.state not in ('choice', 'error', 'uncertain'):
                continue
            # Reload reads Lazada's item status again; it never resubmits an
            # uncertain pack/ready-to-ship request by itself.
            job.write({'state': 'prepare', 'message': False, 'user_id': self.env.uid,
                       'next_run': fields.Datetime.now(), 'attempts': 0})
        self.env.ref('lazada_connector.cron_lazada_fulfillment')._trigger()
        return True

    def action_open(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        return {'type': 'ir.actions.act_window', 'name': 'Lazada Shipment',
                'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'current'}

    def action_retry_label(self):
        require_manager(self)
        for job in self:
            if not job.arranged_at or job.state != 'error':
                raise UserError('Only a failed label for an arranged shipment can be regenerated.')
            job.write({'state': 'shipped', 'message': False, 'attempts': 0,
                       'next_run': fields.Datetime.now()})
        self.env.ref('lazada_connector.cron_lazada_fulfillment')._trigger()
        return True

    def _client(self):
        self.ensure_one()
        order = self.order_id
        order.check_access_rights('write')
        order.check_access_rule('write')
        config = self.config_id
        if not order.is_lazada_order or not order.lazada_order_id or not config or not config.active:
            raise UserError('A real imported Lazada order and an active seller connection are required.')
        if config.company_id != order.company_id:
            raise UserError('Order company does not match the Lazada seller company.')
        if config.region == 'cb':
            raise UserError('Cross-border sellers are not supported; arrange shipment in Seller Center.')
        config.check_access_rights('write')
        config.check_access_rule('write')
        return config._get_api(), config._ensure_valid_token()

    def _items(self, client, token):
        items = client.get_order_items(token, self.order_id.lazada_order_id)
        if isinstance(items, list) and items:
            order = self.order_id
            order.update_lazada_status(order._lazada_summary_status([i.get('status') for i in items]))
        stage, active = classify_items(items)
        package_ids, tracking = packages(active)
        if package_ids:
            self.write({'package_number': ','.join(package_ids),
                        'tracking_number': ','.join(tracking) or False})
        return stage, active

    def _check_sale_order(self):
        order = self.order_id
        if order.state == 'cancel':
            raise UserError('The Odoo sale order is cancelled.')
        lines = order.order_line.filtered(lambda line: not line.display_type)
        if not lines or any(not line.product_id or line.product_id.default_code == 'LAZADA_UNMAPPED' for line in lines):
            raise UserError('Map every order line to a real product before arranging shipment.')
        if self.confirm_sale and order.state in ('draft', 'sent'):
            order.action_confirm()
        if order.state not in ('sale', 'done'):
            raise UserError('Confirm the Odoo sale order before arranging shipment.')

    def _mark_arranged(self):
        self.write({'state': 'shipped', 'arranged_at': self.arranged_at or fields.Datetime.now(), 'message': False})

    def _prepare(self, client, token):
        stage, _active = self._items(client, token)
        if stage == 'arranged':
            self._mark_arranged()
            return
        if (stage == 'pending' and self.shipment_requested_at) or (stage == 'packed' and self.rts_requested_at):
            self.write({'state': 'uncertain', 'message': 'A shipment request was already attempted. Check Seller Center; do not send it again automatically.'})
            return
        if stage == 'packed':
            self.write({'state': 'choice', 'packed_at': self.packed_at or fields.Datetime.now(),
                        'message': 'Already packed on Lazada. Queue this order to set it ready to ship.'})
            return
        self.write({'state': 'choice', 'message': 'Queue this order to pack it and set it ready to ship.'})

    def _ship(self, client, token):
        stage, active = self._items(client, token)
        if stage == 'arranged':
            self._mark_arranged()
            return
        if (stage == 'pending' and self.shipment_requested_at) or (stage == 'packed' and self.rts_requested_at):
            self.write({'state': 'uncertain', 'message': 'A shipment request was previously attempted. Check Seller Center.'})
            return
        self._check_sale_order()
        if stage == 'packed':
            self.write({'state': 'packed', 'packed_at': self.packed_at or fields.Datetime.now(), 'message': False})
            return
        item_ids = [item.get('order_item_id') for item in active]
        if not all(item_ids):
            raise UserError('Lazada returned an order item without an id.')
        order_id = self.order_id.lazada_order_id
        # This method ONLY runs inside the dedicated cron cursor. Persist an intent
        # BEFORE external side effects so crash/timeout recovery cannot replay the pack.
        self.write({'state': 'uncertain', 'shipment_requested_at': fields.Datetime.now(),
                    'message': 'Pack request in progress; check its result before any retry.'})
        self.env.cr.commit()
        try:
            package_ids, tracking, providers = pack_result(client.pack_order(token, order_id, item_ids), order_id)
        except (LazadaAPIError, ShippingRejected) as exc:
            # A parsed business rejection is definitive; timeouts and malformed
            # responses remain uncertain and must only be reconciled.
            if definitive(exc):
                self.write({'state': 'error', 'shipment_requested_at': False, 'message': str(exc)})
                return
            raise
        self.write({'state': 'packed', 'packed_at': fields.Datetime.now(), 'message': False,
                    'package_number': ','.join(package_ids), 'tracking_number': ','.join(tracking) or False,
                    'shipment_provider': ', '.join(providers) or False})

    def _rts(self, client, token):
        stage, active = self._items(client, token)
        if stage == 'arranged':
            self._mark_arranged()
            return
        if stage != 'packed':
            raise UserError('The Lazada order is no longer packed. Reload to check it.')
        if self.rts_requested_at:
            self.write({'state': 'uncertain', 'message': 'A ready-to-ship request was previously attempted. Check Seller Center.'})
            return
        package_ids, _tracking = packages(active)
        if not package_ids:
            raise ShippingPending('Package id is not ready; the worker will check again.')
        self.write({'state': 'uncertain', 'rts_requested_at': fields.Datetime.now(),
                    'message': 'Ready-to-ship request in progress; check its result before any retry.'})
        self.env.cr.commit()
        try:
            rts_result(client.ready_to_ship(token, package_ids), package_ids)
        except (LazadaAPIError, ShippingRejected) as exc:
            if definitive(exc):
                self.write({'state': 'error', 'rts_requested_at': False, 'message': str(exc)})
                return
            raise
        self.write({'state': 'shipped', 'arranged_at': fields.Datetime.now(), 'message': False})

    def _create_label(self, client, token):
        stage, active = self._items(client, token)
        if stage != 'arranged':
            raise UserError('The Lazada order is not ready to ship. Reload to check it.')
        package_ids, tracking = packages(active)
        if not package_ids or not tracking:
            raise ShippingPending('Package or tracking number is not ready; the worker will check again.')
        content, url = document(client.get_awb_document(token, package_ids))
        if not content:
            content = client.download_document(url)
        safe_id = re.sub(r'[^A-Za-z0-9_-]', '_', self.order_id.lazada_order_id)
        self.write({'state': 'ready', 'label_data': base64.b64encode(content),
                    'label_filename': f'lazada_{self.config_id.id}_{safe_id}.pdf', 'message': False})

    def _step(self):
        require_manager(self)
        client, token = self._client()
        getattr(self, {'prepare': '_prepare', 'queued': '_ship', 'packed': '_rts',
                       'shipped': '_create_label'}[self.state])(client, token)

    @api.model
    def cron_process(self):
        """Isolated transactions; session advisory lock survives the intent commit."""
        jobs = self.sudo().search([
            ('state', 'in', list(WORKER_STATES)),
            ('config_id.active', '=', True),
            ('next_run', '<=', fields.Datetime.now()),
        ], order='next_run, id', limit=5)
        for job_id in jobs.ids:
            with Registry(self.env.cr.dbname).cursor() as cr:
                cr.execute('SELECT pg_try_advisory_lock(%s, %s)', (LOCK_KEY, job_id))
                if not cr.fetchone()[0]:
                    continue
                try:
                    admin = api.Environment(cr, SUPERUSER_ID, {})
                    job = admin[self._name].browse(job_id).exists()
                    if not job or job.state not in WORKER_STATES:
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
                            job.write({'state': 'error', 'message': 'Still pending after 20 checks. Retry later.'})
                        job.next_run = fields.Datetime.now() + timedelta(seconds=30)
                        cr.commit()
                    except ShippingPending as exc:
                        job.attempts += 1
                        job.write({'message': str(exc), 'next_run': fields.Datetime.now() + timedelta(minutes=1)})
                        if job.attempts >= 20:
                            job.write({'state': 'error', 'message': 'Package or tracking number still pending after 20 checks. Retry later.'})
                        cr.commit()
                    except Exception as exc:
                        # Preserve committed external intent; roll back only this phase.
                        cr.rollback()
                        admin = api.Environment(cr, SUPERUSER_ID, {})
                        job = admin[self._name].browse(job_id)
                        state = 'uncertain' if job.state == 'uncertain' else 'error'
                        job.write({'state': state, 'message': str(exc)[:2000]})
                        cr.commit()
                        _logger.exception('Lazada fulfillment job %s requires attention', job_id)
                finally:
                    cr.execute('SELECT pg_advisory_unlock(%s, %s)', (LOCK_KEY, job_id))
                    cr.commit()


class SaleOrderFulfillment(models.Model):
    _inherit = 'sale.order'

    def action_lazada_shipping_batch(self):
        require_manager(self)
        if not self or len(self) > 200:
            raise UserError('Select between 1 and 200 Lazada orders per batch.')
        if len(self.company_id) != 1:
            raise UserError('Create separate batches for each company.')
        if any(not o.is_lazada_order or not o.lazada_config_id or not o.lazada_order_id for o in self):
            raise UserError('Select imported Lazada orders with seller connections only.')
        jobs = self.env['lazada.fulfillment.job']
        # Lock all orders in a stable order so concurrent batch creation cannot race.
        self.env.cr.execute('SELECT id FROM sale_order WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
        for order in self:
            job = jobs.search([('order_id', '=', order.id)], limit=1)
            jobs |= job or jobs.create({'order_id': order.id})
        batch = self.env['lazada.fulfillment.batch'].create({
            'company_id': self.company_id.id, 'job_ids': [fields.Command.set(jobs.ids)],
        })
        self.env.ref('lazada_connector.cron_lazada_fulfillment')._trigger()
        return {'type': 'ir.actions.act_window', 'name': 'Lazada Shipping Batch',
                'res_model': batch._name, 'res_id': batch.id, 'view_mode': 'form', 'target': 'current'}
