# -*- coding: utf-8 -*-
# from odoo import http


# class BuzcustomProductSku(http.Controller):
#     @http.route('/buzcustom_product_sku/buzcustom_product_sku', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/buzcustom_product_sku/buzcustom_product_sku/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('buzcustom_product_sku.listing', {
#             'root': '/buzcustom_product_sku/buzcustom_product_sku',
#             'objects': http.request.env['buzcustom_product_sku.buzcustom_product_sku'].search([]),
#         })

#     @http.route('/buzcustom_product_sku/buzcustom_product_sku/objects/<model("buzcustom_product_sku.buzcustom_product_sku"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('buzcustom_product_sku.object', {
#             'object': obj
#         })

