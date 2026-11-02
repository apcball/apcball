# -*- coding: utf-8 -*-
"""Read-only asset subledger figures as of a date, from ORM data only.

Conventions (shared by the reconciliation, roll-forward and ageing reports so
their numbers always agree):
  * An asset is "on the books" at a date when it is capitalized (or later
    disposed), its in-service date is on or before that date, and no POSTED
    disposal dated on or before that date exists.
  * Cost = ``gross_cost``. Accumulated depreciation = posted depreciation lines
    whose entry date is on or before the date, minus lines whose reversal is also
    on or before the date. Planned/exception lines are never counted as posted.
"""
from collections import defaultdict


class AssetLedger:

    def __init__(self, env, company, date):
        self.env, self.company, self.date = env, company, date
        self._live = None

    def disposal_dates(self):
        disposals = self.env['buz.asset.disposal'].search(
            [('company_id', '=', self.company.id), ('state', '=', 'posted')])
        return {d.asset_id.id: d.disposal_date for d in disposals}

    def live_assets(self):
        if self._live is None:
            disposed_at = self.disposal_dates()
            assets = self.env['buz.asset'].with_context(active_test=False).search([
                ('company_id', '=', self.company.id),
                ('accounting_state', 'in', ('capitalized', 'disposed')),
                ('in_service_date', '!=', False), ('in_service_date', '<=', self.date)])
            self._live = assets.filtered(
                lambda a: not disposed_at.get(a.id) or disposed_at[a.id] > self.date)
        return self._live

    def cost_by_asset(self):
        return {a: a.gross_cost for a in self.live_assets()}

    def accumulated_by_asset(self):
        live = self.live_assets()
        result = defaultdict(float)
        lines = self.env['buz.asset.depreciation.line'].search([
            ('asset_id', 'in', live.ids), ('state', 'in', ('posted', 'reversed')), ('move_id', '!=', False)])
        for line in lines:
            if line.move_id.date > self.date:
                continue
            if line.reversal_move_id and line.reversal_move_id.date <= self.date:
                continue
            result[line.asset_id] += line.planned_amount
        return result

    def unposted_due_by_asset(self):
        live = self.live_assets()
        result = defaultdict(float)
        lines = self.env['buz.asset.depreciation.line'].search([
            ('asset_id', 'in', live.ids), ('state', 'in', ('planned', 'exception')),
            ('depreciation_date', '<=', self.date)])
        for line in lines:
            result[line.asset_id] += line.planned_amount
        return result

    def gl_balances(self, accounts):
        """Posted GL balance per account (debit - credit) up to the date, via ORM grouping."""
        if not accounts:
            return {}
        groups = self.env['account.move.line'].read_group(
            [('account_id', 'in', accounts.ids), ('company_id', '=', self.company.id),
             ('parent_state', '=', 'posted'), ('date', '<=', self.date)],
            ['balance:sum'], ['account_id'])
        return {g['account_id'][0]: g['balance'] for g in groups}


def period_movements(env, company, date_from, date_to):
    """Per category: additions, depreciation, disposals (cost and accumulated) in the period."""
    additions, depreciation = defaultdict(float), defaultdict(float)
    disposal_cost, disposal_accum = defaultdict(float), defaultdict(float)
    assets = env['buz.asset'].with_context(active_test=False).search([
        ('company_id', '=', company.id), ('accounting_state', 'in', ('capitalized', 'disposed')),
        ('in_service_date', '>=', date_from), ('in_service_date', '<=', date_to)])
    for asset in assets:
        additions[asset.category_id] += asset.gross_cost
    lines = env['buz.asset.depreciation.line'].search([
        ('company_id', '=', company.id), ('state', 'in', ('posted', 'reversed')), ('move_id', '!=', False)])
    for line in lines:
        category = line.asset_id.category_id
        if date_from <= line.move_id.date <= date_to:
            depreciation[category] += line.planned_amount
        if line.reversal_move_id and date_from <= line.reversal_move_id.date <= date_to:
            depreciation[category] -= line.planned_amount
    disposals = env['buz.asset.disposal'].search([
        ('company_id', '=', company.id), ('state', '=', 'posted'),
        ('disposal_date', '>=', date_from), ('disposal_date', '<=', date_to)])
    for disposal in disposals:
        category = disposal.asset_id.category_id
        disposal_cost[category] += disposal.cost
        disposal_accum[category] += disposal.accumulated_depreciation
    return additions, depreciation, disposal_cost, disposal_accum
