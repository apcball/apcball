# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Keep current users working: grant the new dashboard group to everyone
    who had access through the old gates (Budget User / Invoicing)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    new = env.ref('biz_dashboard_ap_payment.group_ap_payment_dashboard_user', raise_if_not_found=False)
    if not new:
        return
    old = env.ref('biz_monthly_analytic_budget.group_monthly_budget_user', raise_if_not_found=False) \
        | env.ref('account.group_account_invoice', raise_if_not_found=False)
    users = env['res.users'].with_context(active_test=False).search([('groups_id', 'in', old.ids)])
    new.write({'users': [(4, u.id) for u in users]})

    # menuitem groups= is additive on update: drop the old gates from our menus
    menus = env['ir.ui.menu']
    for xid in ('menu_ap_payment_dashboard_budget', 'menu_ap_payment_dashboard_account',
                'menu_ap_dashboard_loan_manual'):
        menus |= env.ref('biz_dashboard_ap_payment.' + xid, raise_if_not_found=False) or menus.browse()
    menus.write({'groups_id': [(6, 0, new.ids)]})
