import base64
import logging

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class WarrantyRegistrationPortal(http.Controller):

    @http.route('/warranty/register', type='http', auth='public', website=True)
    def registration_form(self, **kwargs):
        # No product query needed - user types product name
        return request.render('buz_warranty_portal.registration_form', {
            'defaults': kwargs,
            'errors': {},
        })

    @http.route('/warranty/register/submit', type='http', auth='public',
                website=True, methods=['POST'], csrf=True)
    def registration_submit(self, **post):
        errors = {}

        # required validation
        for key, label in [('partner_name', 'ชื่อ-นามสกุล'), ('phone', 'เบอร์โทรศัพท์'),
                           ('start_date', 'วันที่ซื้อ')]:
            if not (post.get(key) or '').strip():
                errors[key] = _('กรุณากรอก %s') % label


        # date parse
        start_date = False
        if post.get('start_date'):
            try:
                start_date = fields.Date.from_string(post['start_date'])
            except Exception:
                errors['start_date'] = _('รูปแบบวันที่ไม่ถูกต้อง (YYYY-MM-DD)')

        if errors:
            return request.render('buz_warranty_portal.registration_form', {
                'defaults': post, 'errors': errors})

        # find-or-create partner (email exact, else phone exact, else create)
        Partner = request.env['res.partner'].sudo()
        email = (post.get('email') or '').strip()
        phone = (post.get('phone') or '').strip()
        domain = []
        if email:
            domain = [('email', '=ilike', email)]
        elif phone:
            domain = [('phone', '=', phone)]
        partner = Partner.search(domain, limit=1) if domain else Partner
        if not partner:
            partner = Partner.create({
                'name': post['partner_name'].strip(),
                'phone': phone,
                'email': email,
                'street': (post.get('street') or '').strip(),
                'type': 'contact',
            })
        else:
            # fill missing contact info on existing partner
            vals = {}
            if phone and not partner.phone:
                vals['phone'] = phone
            if email and not partner.email:
                vals['email'] = email
            if post.get('street') and not partner.street:
                vals['street'] = post['street'].strip()
            if vals:
                partner.write(vals)

        # serial → store typed value directly (no lot matching without product reference)
        serial = (post.get('serial_number') or '').strip()

        # proof attachments (files)
        att_ids = []
        for f in request.httprequest.files.getlist('proof'):
            if not f or not f.filename:
                continue
            data = base64.b64encode(f.read())
            att = request.env['ir.attachment'].sudo().create({
                'name': f.filename,
                'datas': data,
                'res_model': 'warranty.card',
                'res_id': 0,  # patched after card create
            })
            att_ids.append(att.id)

        # create card in draft
        product_description = (post.get('product_description') or '').strip()
        card_vals = {
            'partner_id': partner.id,
            'lot_id': False,
            'start_date': start_date or fields.Date.today(),
            'state': 'draft',
            'source': 'portal',
            'dealer_name': (post.get('dealer_name') or '').strip(),
            'invoice_number': (post.get('invoice_number') or '').strip(),
            'serial_number_input': serial,
            'product_description': product_description,
            'registration_date': fields.Datetime.now(),
        }
        if att_ids:
            card_vals['proof_attachment_ids'] = [fields.Command.set(att_ids)]

        try:
            card = request.env['warranty.card'].sudo().create(card_vals)
        except Exception as e:
            _logger.warning('warranty.card create failed: %s', e)
            return request.render('buz_warranty_portal.registration_error', {'message': str(e)})

        # patch res_id on attachments
        if att_ids:
            request.env['ir.attachment'].sudo().browse(att_ids).write({'res_id': card.id})

        return request.render('buz_warranty_portal.registration_success', {'card': card})