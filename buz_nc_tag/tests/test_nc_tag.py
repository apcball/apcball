from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNcTag(TransactionCase):

    def test_units_and_render(self):
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal')], limit=1)
        picking_type.is_nc_tag = True
        product = self.env['product.product'].create(
            {'name': 'NC Test', 'default_code': 'NCT1', 'type': 'product'})
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
        })
        self.env['stock.quant']._update_available_quantity(
            product, picking.location_id, 4)
        for qty in (3, 1):
            move = self.env['stock.move'].create({
                'name': 'm', 'product_id': product.id, 'product_uom_qty': qty,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            })
            self.env['stock.move.line'].create({
                'move_id': move.id, 'picking_id': picking.id,
                'product_id': product.id, 'quantity': qty,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            })
        self.assertEqual(len(picking._nc_tag_units()), 4)
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'buz_nc_tag.report_nc_tag', picking.ids)
        body = html.decode()
        self.assertEqual(body.count('class="nc-tag"'), 4)
        self.assertEqual(body.count('class="nc-page"'), 2)  # 3 tags + 1 tag
