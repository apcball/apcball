# -*- coding: utf-8 -*-
{
    'name': 'BUZ Accounting Date Control',
    'version': '17.0.1.0.0',
    'summary': 'Enterprise accounting-date governance: policy hierarchy, validation '
               'chokepoint, approval workflow, and immutable audit log.',
    'description': """
BUZ Accounting Date Control
===========================

Enterprise governance framework for accounting dates on account moves.

Pipeline: Policy Engine -> Validation Engine -> Approval Workflow ->
Immutable Audit Log. See doc/architecture.md (Phase 1) and the Technical
Specification (Phase 2) for the full design.

This build ships the minimal installable spine:
  - buz.accounting.date.company.policy  (per-company back/future-day ceilings)
  - account.move validation chokepoint  (BR-B01 back-day, BR-F01 future-day,
                                         BR-P04 fail-closed, BR-L01 audit)
  - buz.accounting.date.audit.log       (immutable, hash-chained)
  - smoke test (tests/test_backdate_smoke.py)

Approval workflow, override, reports, wizards, and full views are added in
subsequent file-order steps.
""",
    'author': 'Mogen Co.',
    'website': 'https://www.mogen.co.th',
    'category': 'Accounting',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'mail',
    ],
    'data': [
        # Security: groups -> ACL -> record rules
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        # Fail-safe permissive seed (keeps DEV functional; tighten for PROD)
        'data/default_policy_seed.xml',
        # Wizard
        'wizard/date_change_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
