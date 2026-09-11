# -*- coding: utf-8 -*-
"""Relax the per-user record rules on job.cost.sheet / job.order /
material.requisition to company scope only.

The rules live in a `noupdate="1"` data block, so editing the XML alone
does not touch rows created on an already-installed database. Rewrite the
domains here. Internal users linked to POs / vendor bills / payments that
reference these documents were hitting an AccessError because they were
neither the creator nor the assigned project manager / employee.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

COMPANY_SCOPE_DOMAIN = (
    "['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]"
)

RULE_XMLIDS = (
    "job_costing_management.rule_job_cost_sheet_user",
    "job_costing_management.rule_job_order_user",
    "job_costing_management.rule_material_requisition_user",
    "job_costing_management.rule_material_requisition_dept_manager",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in RULE_XMLIDS:
        rule = env.ref(xmlid, raise_if_not_found=False)
        if not rule:
            _logger.warning("relax_record_rules: %s not found, skipped", xmlid)
            continue
        rule.domain_force = COMPANY_SCOPE_DOMAIN
        _logger.info("relax_record_rules: %s -> company scope", xmlid)
