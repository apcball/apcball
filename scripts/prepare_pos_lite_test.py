"""Run through `odoo shell` only, before POS Lite tests on isolated MOG_TEST."""

if env.cr.dbname != 'MOG_TEST':
    raise RuntimeError('POS Lite test setup is restricted to MOG_TEST')

# Payment/return tests need a sales journal and receivable/payable accounts.
# A fresh --without-demo database does not have these until a chart is loaded.
if not env.company.chart_template:
    env['account.chart.template'].try_loading('generic_coa', env.company, install_demo=False)
env.cr.commit()
