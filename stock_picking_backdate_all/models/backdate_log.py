# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models, _


class StockBackdateLog(models.AbstractModel):
    _name = 'stock.backdate.log'
    _description = "Backdate Chatter Log"

    @api.model
    def _log_backdate(self, record, old_date, new_date, moves, reason=None):
        """Write who moved which date on the chatter of ``record``.

        A log note: no e-mail is sent and the author does not need an e-mail
        address, so logging can never block a backdate.
        """
        def local(value):
            if not value:
                return '-'
            return fields.Datetime.context_timestamp(record, value).strftime(
                '%d/%m/%Y %H:%M:%S')

        layers = self.env['stock.valuation.layer'].sudo().search(
            [('stock_move_id', 'in', moves.ids)])
        items = [Markup('<li>%s %s → %s</li>') % (
            _("วันที่:"), local(old_date), local(new_date))]
        if reason:
            items.append(Markup('<li>%s %s</li>') % (_("เหตุผล:"), reason))
        items.append(Markup('<li>%s</li>') % _(
            "รายการที่แก้: stock move %s, move line %s, valuation layer %s, "
            "journal entry %s",
            len(moves), len(moves.move_line_ids), len(layers),
            len(layers.account_move_id)))
        body = Markup('<p><b>Backdate</b> %s %s</p><ul>%s</ul>') % (
            _("โดย"), self.env.user.name, Markup('').join(items))
        record._message_log(body=body)
