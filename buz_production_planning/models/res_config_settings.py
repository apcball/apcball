# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

PREFIX = 'buz_production_planning.'


def get_plan_config(env):
    """Return the planning configuration as a plain dict (typed)."""
    icp = env['ir.config_parameter'].sudo()

    def _get(key, default):
        return icp.get_param(PREFIX + key, default)

    cutoff = _get('history_cutoff', '2026-04-01')
    try:
        cutoff = fields.Date.to_date(cutoff)
    except (ValueError, TypeError) as exc:
        raise UserError(_(
            "Planning setting 'History cut-off date' is not a valid date (%s). "
            "Fix it in Production Planning > Configuration > Settings.", cutoff)) from exc
    codes = [c.strip() for c in (_get('supply_warehouse_codes', '') or '').split(',') if c.strip()]
    return {
        'warehouse_codes': codes,
        'lead_make_days': float(_get('lead_make_days', 3)),
        'lead_buy_days': float(_get('lead_buy_days', 7)),
        'horizon_weeks': int(_get('horizon_weeks', 8)),
        'lookback_weeks': int(_get('lookback_weeks', 12)),
        'history_cutoff': cutoff or date(2026, 4, 1),
        'min_history_wo': int(_get('min_history_wo', 5)),
        'expected_factor': float(_get('expected_factor', 1.0)),
    }


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    plan_supply_warehouse_ids = fields.Many2many(
        'stock.warehouse', 'plan_settings_supply_wh_rel', 'settings_id', 'warehouse_id',
        string="Supply Warehouses",
        help="Warehouses counted as available supply by default in a new plan.")
    plan_lead_make_days = fields.Float(
        string="Default Manufacturing Lead Time (days)",
        config_parameter='buz_production_planning.lead_make_days')
    plan_lead_buy_days = fields.Float(
        string="Default Purchase Lead Time (days)",
        config_parameter='buz_production_planning.lead_buy_days')
    plan_horizon_weeks = fields.Integer(
        string="Planning Horizon (weeks)",
        config_parameter='buz_production_planning.horizon_weeks')
    plan_lookback_weeks = fields.Integer(
        string="Forecast Look-back (weeks)",
        config_parameter='buz_production_planning.lookback_weeks')
    plan_history_cutoff = fields.Date(
        string="History Cut-off Date",
        help="Data before this date is never used for forecasts or averages.")
    plan_min_history_wo = fields.Integer(
        string="Minimum Workorders for Reliable History",
        config_parameter='buz_production_planning.min_history_wo')
    plan_expected_factor = fields.Float(
        string="Expected Duration Factor",
        config_parameter='buz_production_planning.expected_factor',
        help="Multiplier applied to the expected duration when an operation has no reliable history.")

    @api.model
    def get_values(self):
        res = super().get_values()
        cfg = get_plan_config(self.env)
        warehouses = self.env['stock.warehouse'].search([('code', 'in', cfg['warehouse_codes'])])
        res.update(
            plan_supply_warehouse_ids=[fields.Command.set(warehouses.ids)],
            plan_history_cutoff=cfg['history_cutoff'],
        )
        return res

    def set_values(self):
        res = super().set_values()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param(PREFIX + 'supply_warehouse_codes',
                      ','.join(self.plan_supply_warehouse_ids.mapped('code')))
        if self.plan_history_cutoff:
            icp.set_param(PREFIX + 'history_cutoff', fields.Date.to_string(self.plan_history_cutoff))
        return res
