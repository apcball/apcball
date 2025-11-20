Prompt: Odoo 17 Module – FX Journal Entry for Import Goods (WIP Inventory + AP Foreign)

Goal
Create an Odoo 17 custom module that supports import purchases in foreign currency (e.g. USD).
The module adds a wizard + button on Vendor Bill to:

Use an FX rate based on a date specified by the user.

Post accounting entries to:

Reclass WIP Inventory (สินค้าระหว่างทาง) to AP Foreign (เจ้าหนี้การค้าต่างประเทศ).

If there is any FX difference between original bill posting and the new rate, create one extra journal line for FX Diff (gain/loss).

Allow configuration of related accounts via settings using Account Code (not only M2O account).

Module Info

Module technical name: account_import_fx_wip

Version: 17.0

Depends:

account

base

Installable: True

Application: False

Business Concept (บอล)

Scenario (Import from foreign supplier):

เปิด PO และ Create Bill (Vendor Bill in USD)

Bill currency: USD

Bill is posted using FX rate on bill date.

Accounting entry at bill posting:

Dr WIP Inventory (สินค้าระหว่างทาง)

Cr Purchase (ซื้อสินค้า)

Payment in USD may be processed separately (out of scope for now).

เมื่อสินค้าถึงคลัง / ต้องการปรับจาก WIP → AP Foreign

เมื่อสินค้าถึง (หรือเมื่อ user ต้องการตัด WIP ออกมาเป็นเจ้าหนี้แทน)

User กดปุ่มที่ Bill → เปิด Wizard

User เลือกวันที่สำหรับใช้เรต เช่น:

วันที่สินค้ามาถึง

หรือวันที่ต้องการบันทึกเจ้าหนี้การค้าต่างประเทศ

Module จะ:

ใช้เรต ณ วันที่ user ระบุ

เปรียบเทียบมูลค่าในบริษัท (THB) ระหว่าง:

มูลค่าจากการลงบิลเดิม

มูลค่าแปลงใหม่ด้วยเรตวันที่ user เลือก

ทำ JE:

Cr WIP Inventory (สินค้าระหว่างทาง)

Dr AP Foreign (เจ้าหนี้การค้าต่างประเทศ)

ถ้ามีส่วนต่างอัตราแลกเปลี่ยน:

สร้าง รายการ Diff อีก 1 บรรทัด (FX Gain/Loss) ใน JE เดียวกัน

Settings – Account Code Configuration

Add configuration by Account Code in settings:

In res.company (via res.config.settings):

wip_account_code (Char)

Code of WIP Inventory account (สินค้าระหว่างทาง)

ap_foreign_account_code (Char)

Code of AP Foreign account (เจ้าหนี้การค้าต่างประเทศ)

fx_gain_account_code (Char)

Code of FX gain account

fx_loss_account_code (Char)

Code of FX loss account

Behavior:

When module needs an account:

Search account.account by company_id and code = <code from setting>.

If not found → raise UserError with clear message, e.g.:

"Cannot find WIP account with code %s in company %s".

Configuration UI:

res.config.settings fields:

wip_account_code

ap_foreign_account_code

fx_gain_account_code

fx_loss_account_code

Show in Accounting settings view with labels in English, ready for translation.

Wizard – Reclass WIP to AP Foreign with FX Rate

Create Transient Model: import.fx.wip.wizard

Fields:

bill_id (Many2one account.move, required)

Vendor Bill only (move_type = 'in_invoice').

date (Date, required)

Date to use for FX rate.

Default: bill date (bill_id.invoice_date) or today.

company_id (Many2one res.company, readonly)

Default: bill_id.company_id.

currency_id (Many2one res.currency, readonly)

Default: bill_id.currency_id.

journal_id (Many2one account.journal, required)

Domain: type = 'general' or a specific FX journal.

rate (Float, digits=Rate)

FX rate used for conversion at date.

Default: fetched automatically from res.currency.rate.

Allow manual override (user can edit).

amount_foreign (Monetary, in currency_id, readonly)

Total amount in foreign currency to be reclassed (from bill).

amount_company_original (Monetary, in company currency, readonly)

THB amount from original bill posting.

amount_company_new (Monetary, in company currency, readonly)

Recomputed THB amount using rate and amount_foreign.

difference_amount (Monetary, in company currency, readonly)

amount_company_new - amount_company_original.

Behavior:

When wizard opens:

Prefill bill_id, company_id, currency_id.

Compute:

amount_foreign: from bill total in currency (e.g. bill.amount_total_in_currency or relevant WIP amount).

amount_company_original: from bill posting in company currency (THB).

Fetch FX rate for currency_id vs company_id.currency_id at date:

Use res.currency._get_rates or equivalent Odoo 17 standard method.

If no rate on that date, use latest on or before.

If no rate found at all → raise UserError.

When user changes date or rate:

Recompute amount_company_new = amount_foreign * rate.

Recompute difference_amount.

Wizard has button: "Create Journal Entry" → method action_create_import_fx_wip_entry.

Journal Entry Logic

When user confirms:

Resolve accounts by code from company settings:

wip_account from wip_account_code

ap_foreign_account from ap_foreign_account_code

fx_gain_account from fx_gain_account_code

fx_loss_account from fx_loss_account_code

If any missing → raise UserError.

Determine difference sign

diff = difference_amount

If diff > 0 → gain or loss depending on design below.

If diff < 0 → opposite.

Design: Treat amount_company_new as the new carrying amount of AP Foreign.
Compare with original WIP THB amount.

Create Journal Entry (account.move)

date = wizard date

journal_id = wizard journal_id

ref = "Import FX Reclass for Bill %s" % bill_id.name

line_ids:

Line 1: Reclass WIP → AP Foreign (base amount):

Cr WIP Inventory (สินค้าระหว่างทาง)

account: wip_account

amount: amount_company_original (company currency)

Dr AP Foreign (เจ้าหนี้การค้าต่างประเทศ)

account: ap_foreign_account

partner: bill_id.partner_id

amount: amount_company_new −/+ FX diff handled below (see balancing).

FX Diff Line (only 1 line):

If difference_amount != 0:

Choose account:

If difference_amount > 0 → FX Gain: use fx_gain_account

If difference_amount < 0 → FX Loss: use fx_loss_account

Create one extra journal line:

account: fx_gain_account or fx_loss_account

debit/credit:

Must balance the move.

Example option:

Use amount_company_original on WIP line.

Use amount_company_original on AP Foreign line.

Put whole difference_amount on FX account.

You can implement standard FX pattern:

If amount_company_new > amount_company_original:

Extra Dr Loss / Cr Gain accordingly, to offset difference.

Important: final JE must be balanced in company currency.

Posting & Linking

Post the JE automatically (action_post()).

Add field on JE:

bill_id (Many2one account.move) to link back to the Vendor Bill.

Possibly is_import_fx_wip_entry (Boolean) to flag this as system-generated entry.

On Bill (account.move):

Add One2many:

import_fx_wip_entry_ids → account.move (those JEs).

Add smart button "Import FX Entries":

show the count

open list of related JEs.

Bill Form View Changes

On account.move form (Vendor Bill):

Add header button:

Label: "Create Import FX Entry"

type="action" or object calling method on account.move:

This method opens the wizard with context bill_id.

Visible only when:

move_type = 'in_invoice'

state = 'posted'

currency_id != company_id.currency_id (foreign currency only) – configurable if needed.

Add smart button:

Label: "Import FX Entries"

Show number of related import_fx_wip_entry_ids.

Models & Files

Python

models/account_move.py

Extend account.move:

Fields:

import_fx_wip_entry_ids (One2many to account.move, inverse bill_id).

Method:

action_open_import_fx_wip_wizard (open wizard).

Extend account.move (Journal Entry) to add:

bill_id (Many2one to account.move – vendor bill).

is_import_fx_wip_entry (Boolean).

models/import_fx_wip_wizard.py

TransientModel implementing fields + FX logic + action_create_import_fx_wip_entry.

models/res_config_settings.py

fields: wip_account_code, ap_foreign_account_code, fx_gain_account_code, fx_loss_account_code

related to res.company.

XML

views/account_move_views.xml

Inherit vendor bill form:

Add header button.

Add smart button.

views/import_fx_wip_wizard_views.xml

Wizard form.

views/res_config_settings_views.xml

Add fields in Accounting settings.

security/ir.model.access.csv

Access for wizard + any new models.

security/security.xml

Restrict creation/use to accounting groups (e.g. account.group_account_manager).

Error Handling

If any of these missing:

FX rate

WIP account code

AP foreign account code

FX gain/loss account code

→ raise UserError with clear message what to fix in settings.

Deliverables

AI should generate:

Full module structure with working code (Python + XML).

Proper __manifest__.py.

Comments in code explaining:

Where WIP → AP reclass happens.

Where FX difference 1 line is created.

Ready to install on Odoo 17 CE/EE.