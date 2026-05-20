# 🧠 ROLE
You are a senior Odoo 17 architect and backend engineer specializing in accounting and ERP systems.

You must generate **production-grade Odoo module code** with clean architecture, correct accounting logic, and scalable design.

---

# 🎯 OBJECTIVE

Build a complete **Retention Management System** in **ONE single module**:

👉 Module name:
account_retention

---

# 🧩 SCOPE

The module must cover BOTH:

## ✅ Phase 1 (Core Accounting)
- Retention receivable/payable
- Invoice integration
- Retention tracking
- Basic release

## ✅ Phase 2 (Advanced)
- Contract-based retention
- Multi-stage retention rules
- Milestone-based release
- Retention certificate workflow

---

# 📦 MODULE STRUCTURE

You MUST generate:

account_retention/
- __manifest__.py
- models/
- views/
- security/
- data/

---

# 📚 BUSINESS LOGIC

## 1. Retention Concept

- Retention is NOT a discount
- Must use separate accounts:
  - Retention Receivable (asset)
  - Retention Payable (liability)

---

## 2. Invoice Behavior

When invoice is posted:
- create retention lines
- DO NOT release retention immediately

---

## 3. Retention States

Each retention line must support:
- pending
- eligible
- released

---

## 4. Release Logic

### Time-based
- release when release_date reached

### Milestone-based
- release when milestone is done

### Manual
- release via certificate approval

---

## 5. Accounting Logic

### Invoice Stage
- record full revenue/expense
- retention only tracked

---

### Release Stage

Customer:
Dr Accounts Receivable  
Cr Retention Receivable  

Vendor:
Dr Retention Payable  
Cr Accounts Payable  

---

# 🧱 MODELS TO IMPLEMENT

## Core

### account.move (inherit)
- retention_term_id
- retention_amount
- retention_line_ids
- contract_id

---

### account.move.retention
- move_id
- contract_id
- amount
- state (pending / eligible / released)
- release_type
- release_date
- milestone_id

---

### account.retention.term
- percentage
- days_to_release
- account_id

---

## Contract (inside same module)

### retention.contract
- partner_id
- contract_value
- retention_terms_ids

---

### retention.contract.term
- percentage
- release_type:
  - time
  - milestone
  - manual
- milestone_id
- days

---

## Certificate

### retention.certificate
- state:
  - draft
  - approved
  - posted

---

### retention.certificate.line
- retention_line_id
- amount

---

## Milestone Integration

Extend:
project.milestone

Add:
- retention_release flag

---

# ⚙️ AUTOMATION

## Cron Job
- auto-evaluate time-based retention

---

## Event Trigger
- milestone completion triggers retention evaluation

---

# 🖥️ UI REQUIREMENTS

## Contract
- form view
- editable retention terms (tree)

---

## Invoice
- show retention summary
- smart button → retention lines

---

## Retention Entries
- tree view
- filters:
  - pending
  - eligible
  - released

---

## Certificate
- form view
- buttons:
  - approve
  - post

---

## Menu

Accounting > Retention
- Contracts
- Retention Entries
- Certificates

---

# 🔐 SECURITY

- Accountant → full access
- Manager → approve certificate

---

# 🏗️ CODING RULES

You MUST:
- follow Odoo 17 API
- use @api.depends properly
- add docstrings
- no hardcoded IDs
- multi-company safe
- no TODO
- no pseudo code

---

# 📤 OUTPUT FORMAT

For EVERY file:

# === file: account_retention/path/file_name ===
<code>

---

# ⚠️ IMPORTANT

- Everything must be in ONE module only
- Do NOT split into multiple modules
- Keep code clean and modular internally (services, methods)

---

# 🔥 FINAL GOAL

The module must:
- install without errors
- support real accounting workflows
- be production-ready
- be extendable later (can split into modules in future)

---

# 🚀 GENERATE FULL MODULE NOW