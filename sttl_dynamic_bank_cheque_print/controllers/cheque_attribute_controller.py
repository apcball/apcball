from odoo import http
from odoo.http import request


class ChequeAttributeController(http.Controller):

    @http.route('/cheque/configure_attributes', type='http', auth='user', website=True)
    def configure_attributes_page(self, **kwargs):
        cheque_id = kwargs.get('cheque_id')
        if not cheque_id:
            return request.redirect('/error_page')

        cheque = request.env['bank.cheque'].sudo().browse(int(cheque_id))
        cheque_attributes = request.env['cheque.attribute'].sudo().search([('cheque_id', '=', cheque.id)])

        return request.render('sttl_dynamic_bank_cheque_print.cheque_configure_template', {
            'cheques': cheque_attributes,
            'image': cheque.cheque_image,
            # 'cheques': cheque,
            # 'attributes': cheque_attributes,
        })

    @http.route('/update_cheque_attribute', type='json', auth='user')
    def update_cheque_attribute(self, attribute_id, x1, y1, x2, y2):
        cheque_attribute = request.env['cheque.attribute'].sudo().browse(int(attribute_id))
        if cheque_attribute.exists():
            cheque_attribute.write({
                'x1': int(x1),
                'y1': int(y1),
                'x2': int(x2),
                'y2': int(y2),
            })
            return {'status': 'success'}
        return {'status': 'error'}

    @http.route('/get_cheque_attribute', type='json', auth='public')
    def get_cheque_attribute(self, attribute_id):
        attribute = request.env['cheque.attribute'].sudo().search_read(
            [('id', '=', int(attribute_id))],
            ['x1', 'y1', 'x2', 'y2'], limit=1
        )
        if attribute:
            return {'status': 'success', 'data': attribute[0]}
        return {'status': 'error', 'message': 'Attribute not found'}

    @http.route('/save_all_cheque_positions', type='json', auth='user')
    def save_all_cheque_positions(self, positions):
        for pos in positions:
            attribute = request.env['cheque.attribute'].sudo().browse(pos['id'])
            if attribute.exists():
                attribute.write({
                    'x1_position': int(pos['x1']),
                    'y1_position': int(pos['y1']),
                    'x2_position': int(pos['x2']),
                    'y2_position': int(pos['y2']),
                })
        return {'status': 'success'}
