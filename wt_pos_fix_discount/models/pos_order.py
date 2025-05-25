# -*- coding: utf-8 -*-
from odoo import api, fields, models

class PosOrderLine(models.Model):
	_inherit = 'pos.order.line'

	discount_fix = fields.Float(string='Discount (Fix)', digits=0, default=0.0)
	discount_percentage = fields.Float(string='Discount (%)', readonly=True, digits=0, compute="_compute_discount_display")

	def _export_for_ui(self, orderline):
		res = super(PosOrderLine, self)._export_for_ui(orderline)
		res['fix_discount'] = orderline.discount_fix
		return res

	def _order_line_fields(self, line, session_id=None):
		res = super(PosOrderLine, self)._order_line_fields(line, session_id)
		res[2]['discount_fix'] = line[2]['fix_discount']
		return res

	@api.depends('discount_fix','discount')
	def _compute_discount_display(self):
		for line in self:
			if line.discount_fix:
				line.discount_percentage = 0.0
			else:
				line.discount_percentage = line.discount