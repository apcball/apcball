# Settlement Feature - Technical Documentation
## Employee Advance Module

### Architecture Overview

The Settlement feature is implemented as a wizard (transient model) that creates accounting entries to close or reduce employee advance box balances.

```
┌─────────────────────────────────────────────────────────────┐
│                    Settlement Architecture                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────┐         ┌───────────────────┐          │
│  │ Advance Box    │────────>│ Settlement Wizard │          │
│  │ (Model)        │         │ (TransientModel)  │          │
│  └────────────────┘         └───────────────────┘          │
│         │                            │                       │
│         │                            │                       │
│         │                            v                       │
│         │                   ┌─────────────────┐             │
│         │                   │ Account Move    │             │
│         │                   │ (Journal Entry) │             │
│         │                   └─────────────────┘             │
│         │                            │                       │
│         v                            v                       │
│  ┌────────────────────────────────────────┐                │
│  │         Account Move Line              │                │
│  │    (Dr/Cr with partner filtering)      │                │
│  └────────────────────────────────────────┘                │
│                     │                                         │
│                     v                                         │
│         ┌─────────────────────┐                             │
│         │ Auto Reconciliation │                             │
│         └─────────────────────┘                             │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
employee_advance/
├── models/
│   └── advance_box.py              # Main model with settlement action
├── wizards/
│   ├── __init__.py                 # Import settlement_wizard
│   └── settlement_wizard.py        # Settlement wizard implementation
├── views/
│   ├── advance_box_views.xml       # Settlement button in box form
│   └── advance_settlement_wizard_views.xml  # Wizard UI
└── data/
    └── (no specific data file needed)
```

---

## Model: advance.settlement.wizard

### Model Definition

```python
class AdvanceSettlementWizard(models.TransientModel):
    _name = 'advance.settlement.wizard'
    _description = 'Advance Settlement Wizard'
```

### Key Fields

#### Core Fields
```python
box_id                 # Link to advance box (required, readonly)
employee_id            # Related employee (computed from box)
current_balance        # Current balance (computed)
settlement_date        # Date for journal entry (required)
journal_id            # Bank/Cash journal for payment
```

#### Configuration Fields
```python
amount_mode           # 'full' or 'partial'
amount_to_settle      # Amount for partial settlement
scenario              # Settlement type (3 options)
writeoff_policy       # For write-off scenario
writeoff_account_id   # Account for write-off
```

#### Computed Fields
```python
target_amount         # Final amount to settle
direction             # Balance direction (positive/negative)
currency_id           # From advance box
company_id            # From advance box
```

#### Workflow Fields
```python
memo                  # Transaction description
auto_reconcile        # Enable auto reconciliation
create_activity       # Create follow-up activity
activity_user_id      # Activity assignee
activity_type_id      # Activity type
activity_note         # Activity notes
```

---

## Settlement Scenarios

### 1. Pay Employee (pay_employee)

**Condition:** `current_balance > 0` (company owes employee)

**Journal Entry:**
```python
Line 1 (Debit):
    account_id: box.account_id (141101)
    partner_id: employee_partner
    debit: target_amount
    credit: 0.0

Line 2 (Credit):
    account_id: journal.default_account_id
    partner_id: employee_partner
    debit: 0.0
    credit: target_amount
```

**Validation:**
- Requires bank/cash journal
- Balance must be positive
- Journal must have default_account_id

---

### 2. Employee Refund (employee_refund)

**Condition:** `current_balance < 0` (employee owes company)

**Journal Entry:**
```python
Line 1 (Debit):
    account_id: journal.default_account_id
    partner_id: employee_partner
    debit: target_amount
    credit: 0.0

Line 2 (Credit):
    account_id: box.account_id (141101)
    partner_id: employee_partner
    debit: 0.0
    credit: target_amount
```

**Validation:**
- Requires bank/cash journal
- Balance must be negative
- Journal must have default_account_id

---

### 3. Write-off (write_off)

**Sub-scenarios:**

#### A. Expense Write-off (writeoff_policy='expense')
```python
Line 1 (Debit):
    account_id: writeoff_account_id
    partner_id: employee_partner
    debit: target_amount
    credit: 0.0

Line 2 (Credit):
    account_id: box.account_id (141101)
    partner_id: employee_partner
    debit: 0.0
    credit: target_amount
```

#### B. Other Income (writeoff_policy='other_income')
```python
Line 1 (Debit):
    account_id: box.account_id (141101)
    partner_id: employee_partner
    debit: target_amount
    credit: 0.0

Line 2 (Credit):
    account_id: writeoff_account_id
    partner_id: employee_partner
    debit: 0.0
    credit: target_amount
```

**Validation:**
- Requires writeoff_account_id
- Can use general journal
- No balance direction restriction

---

## Key Methods

### 1. default_get(fields)

**Purpose:** Initialize wizard with context data

**Logic:**
```python
1. Get advance box from context
2. Determine default scenario based on balance:
   - balance > 0 → 'pay_employee'
   - balance < 0 → 'employee_refund'
3. Set default journal from box or find bank/cash journal
4. Set current balance and memo
```

**Returns:** Dictionary with default values

---

### 2. _validate_settlement()

**Purpose:** Validate all parameters before creating journal entry

**Validations:**
```python
1. Balance Check:
   - Cannot settle if balance ≈ 0

2. Lock Date Check:
   - settlement_date > fiscal_lock_date
   - settlement_date > period_lock_date

3. Scenario Validation:
   - pay_employee: balance must be > 0
   - employee_refund: balance must be < 0

4. Journal Validation:
   - pay_employee/employee_refund: must be bank/cash
   - Journal must have default_account_id

5. Partner Validation:
   - Employee must have partner configured

6. Account Validation:
   - Advance box must have account_id set

7. Write-off Validation:
   - writeoff_account_id required when policy ≠ 'none'
```

**Raises:** `UserError` or `ValidationError` on failure

---

### 3. _create_settlement_move()

**Purpose:** Create the accounting journal entry

**Process:**
```python
1. Get employee partner:
   - Try address_home_id
   - Fallback to user.partner_id
   - Fallback to address_id
   - Create new partner if needed

2. Determine journal:
   - Use self.journal_id for payment scenarios
   - Use general journal for write-off

3. Build move_vals:
   - Set journal, date, ref, company
   - Ensure journal has sequence

4. Build line items based on scenario:
   - Create debit line
   - Create credit line
   - Set partner on both lines

5. Create account.move

6. Return move (unposted)
```

**Returns:** `account.move` record

---

### 4. _reconcile_141101_lines(move)

**Purpose:** Auto-reconcile advance account lines

**Algorithm:**
```python
1. Find all unreconciled 141101 lines:
   - account_id = box.account_id
   - partner_id = employee_partner
   - reconciled = False
   - move.state = 'posted'

2. Separate debit and credit lines

3. For each debit line:
   - Find matching credit line(s)
   - Same currency
   - Non-zero residual
   - Attempt reconciliation
   - Break on success

4. Handle partial reconciliation
```

**Features:**
- Skipped if `auto_reconcile = False`
- Handles multiple open lines
- Matches by currency
- Uses Odoo's built-in reconciliation

---

### 5. action_settle_advance()

**Purpose:** Main action method to process settlement

**Workflow:**
```python
1. Validate settlement parameters
   → _validate_settlement()

2. Log settlement attempt
   → logger.info with details

3. Create journal entry
   → _create_settlement_move()

4. Post the journal entry
   → move.action_post()

5. Auto-reconcile (if enabled)
   → _reconcile_141101_lines(move)

6. Recompute advance box balance
   → box._trigger_balance_recompute()

7. Post message to advance box
   → box.message_post()

8. Create follow-up activity (if requested)
   → box.activity_schedule()

9. Return action to view journal entry

Error Handling:
   → Catch exceptions
   → Log error
   → Raise UserError with message
```

**Returns:** `ir.actions.act_window` to view created move

---

## Integration Points

### 1. Advance Box Model

**Method:** `action_open_settlement_wizard()`

```python
def action_open_settlement_wizard(self):
    """Open settlement wizard for this advance box"""
    wizard = self.env['advance.settlement.wizard'].create({
        'box_id': self.id,
    })
    return {
        'name': _('Settle Advance'),
        'type': 'ir.actions.act_window',
        'res_model': 'advance.settlement.wizard',
        'res_id': wizard.id,
        'view_mode': 'form',
        'target': 'new',
        'context': {
            'default_box_id': self.id,
            'default_employee_name': self.employee_id.name,
        }
    }
```

**Called from:**
- Advance box form view header button
- Advance box button box stat button

---

### 2. Balance Computation

**Integration:** Settlement triggers balance recompute

```python
# In action_settle_advance()
try:
    self.box_id._trigger_balance_recompute()
except Exception as e:
    _logger.warning("Balance recompute failed: %s", str(e))
```

**Why:** Ensure balance reflects new journal entries immediately

---

### 3. Partner Resolution

**Method:** `box._get_employee_partner()`

**Fallback chain:**
1. `employee.address_home_id` (from hr_contract)
2. `employee.user_id.partner_id`
3. `employee.address_id` (work address)
4. Search for existing partner by name
5. Create new partner with employee name

**Critical:** Must have partner for proper accounting separation

---

## Database Schema

### Wizard Table (Transient)
```sql
CREATE TABLE advance_settlement_wizard (
    id SERIAL PRIMARY KEY,
    create_uid INTEGER,
    create_date TIMESTAMP,
    write_uid INTEGER,
    write_date TIMESTAMP,
    
    -- Core fields
    box_id INTEGER NOT NULL,
    settlement_date DATE NOT NULL,
    journal_id INTEGER,
    
    -- Configuration
    amount_mode VARCHAR,
    amount_to_settle NUMERIC,
    scenario VARCHAR NOT NULL,
    writeoff_policy VARCHAR,
    writeoff_account_id INTEGER,
    
    -- Options
    memo TEXT,
    auto_reconcile BOOLEAN,
    create_activity BOOLEAN,
    activity_user_id INTEGER,
    activity_type_id INTEGER,
    activity_note TEXT,
    
    FOREIGN KEY (box_id) REFERENCES employee_advance_box(id)
);
```

**Note:** Transient model data is auto-cleaned by Odoo scheduler

---

## Security & Permissions

### Access Control

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_advance_settlement_wizard_user,User Settlement Access,model_advance_settlement_wizard,hr.group_hr_user,1,1,1,1
access_advance_settlement_wizard_manager,Manager Settlement Access,model_advance_settlement_wizard,hr.group_hr_manager,1,1,1,1
```

**Access:**
- HR User: Can create settlements for assigned employees
- HR Manager: Can create settlements for all employees

### Record Rules

```xml
<!-- Optional: Restrict by department/company -->
<record id="advance_settlement_wizard_company_rule" model="ir.rule">
    <field name="name">Settlement: Multi-company</field>
    <field name="model_id" ref="model_advance_settlement_wizard"/>
    <field name="domain_force">['|',('company_id','=',False),('company_id','in',company_ids)]</field>
</record>
```

---

## Testing

### Unit Tests

```python
class TestAdvanceSettlement(TransactionCase):
    
    def setUp(self):
        super().setUp()
        self.employee = self.env['hr.employee'].create({...})
        self.advance_box = self.env['employee.advance.box'].create({...})
        
    def test_pay_employee_scenario(self):
        """Test pay employee settlement creates correct journal entry"""
        # Create positive balance
        # Open settlement wizard
        # Process settlement
        # Assert journal entry created
        # Assert balance updated
        
    def test_employee_refund_scenario(self):
        """Test employee refund settlement"""
        # Similar to above
        
    def test_write_off_expense(self):
        """Test write-off to expense"""
        # Create balance
        # Process write-off
        # Assert correct accounts used
        
    def test_validation_zero_balance(self):
        """Test cannot settle zero balance"""
        with self.assertRaises(UserError):
            # Try to settle zero balance
            
    def test_validation_scenario_mismatch(self):
        """Test scenario must match balance direction"""
        with self.assertRaises(ValidationError):
            # Try pay_employee with negative balance
```

### Integration Tests

```python
class TestSettlementIntegration(TransactionCase):
    
    def test_settlement_with_reconciliation(self):
        """Test settlement with auto-reconciliation"""
        # Create multiple advance entries
        # Process settlement
        # Assert lines reconciled
        
    def test_settlement_with_activity(self):
        """Test settlement creates follow-up activity"""
        # Process settlement with activity
        # Assert activity created
        # Assert correct assignee
```

---

## Performance Considerations

### Optimization Points

1. **Partner Resolution:**
   - Cache employee partner lookups
   - Minimize database queries

2. **Balance Computation:**
   - Use indexed fields (account_id, partner_id)
   - Batch operations when possible

3. **Reconciliation:**
   - Limit search to recent unreconciled lines
   - Use SQL-level filtering

4. **Journal Sequence:**
   - Pre-create sequences for journals
   - Avoid sequence creation during settlement

### Query Optimization

```python
# Good: Single query with proper indexing
lines = self.env['account.move.line'].search([
    ('account_id', '=', account_id),
    ('partner_id', '=', partner_id),
    ('reconciled', '=', False),
    ('move_id.state', '=', 'posted')
], limit=100)

# Bad: Multiple queries
for move in moves:
    for line in move.line_ids:
        if line.account_id == account_id:
            # Process...
```

---

## Troubleshooting

### Common Issues

#### 1. Partner Not Found

**Symptom:** Error "Cannot find employee partner"

**Cause:** Employee has no partner configured

**Solution:**
```python
# Automatic partner creation added in v17.0.1.0.4
# Fallback creates partner with employee name
```

#### 2. Journal Sequence Missing

**Symptom:** Error "No sequence defined for journal"

**Cause:** Journal has no sequence configured

**Solution:**
```python
# Automatic sequence creation in _create_settlement_move()
self.env['hr.expense.advance.journal.utils'].ensure_journal_sequence(journal)
```

#### 3. Lock Date Violation

**Symptom:** Error "Cannot post entries in locked period"

**Cause:** `settlement_date <= fiscal_lock_date`

**Solution:**
- Choose date after lock date
- Or unlock the period (if authorized)

#### 4. Reconciliation Fails

**Symptom:** Lines not reconciled after settlement

**Causes:**
- Different currencies
- Already reconciled
- Wrong partner

**Debug:**
```python
# Check line details
_logger.info("Line: %s, Account: %s, Partner: %s, Reconciled: %s",
            line.id, line.account_id.code, line.partner_id.name,
            line.reconciled)
```

---

## Logging & Monitoring

### Log Levels

```python
_logger.info("🏦 SETTLEMENT: Starting settlement...")
_logger.info("🏦 SETTLEMENT: Created journal entry %s", move.name)
_logger.info("🏦 SETTLEMENT: Posted journal entry %s", move.name)
_logger.info("🏦 SETTLEMENT: Attempting auto-reconciliation")
_logger.info("✅ SETTLEMENT: Successfully completed")

_logger.warning("⚠️ Balance recompute failed: %s", str(e))

_logger.error("❌ SETTLEMENT: Failed to settle: %s", str(e))
```

### Log Format

```
🏦 SETTLEMENT: Starting settlement for advance box 42 (employee: John Doe)
🏦 SETTLEMENT: Scenario: pay_employee, Amount: 5000.0, Date: 2024-12-13
🏦 SETTLEMENT: Created journal entry MISC/2024/0123
🏦 SETTLEMENT: Posted journal entry MISC/2024/0123
🏦 SETTLEMENT: Attempting auto-reconciliation
💰 BALANCE REFRESH: Starting for box 42
💰 BALANCE REFRESH: Completed for box 42, new balance: 0.0
✅ SETTLEMENT: Successfully completed settlement for advance box 42
```

### Monitoring Queries

```sql
-- Find recent settlements
SELECT am.name, am.date, am.ref, am.amount_total
FROM account_move am
WHERE am.ref LIKE '%Settlement%'
  AND am.date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY am.date DESC;

-- Check reconciliation status
SELECT aml.id, aml.name, aml.debit, aml.credit, aml.reconciled
FROM account_move_line aml
WHERE aml.account_id IN (
    SELECT id FROM account_account WHERE code LIKE '141101%'
)
AND aml.reconciled = FALSE;
```

---

## Maintenance

### Regular Tasks

1. **Monthly:**
   - Review unreconciled 141101 lines
   - Check for stuck settlements
   - Clear old wizard records

2. **Quarterly:**
   - Audit settlement entries
   - Review write-off accounts
   - Check partner configurations

3. **Yearly:**
   - Review and update write-off policies
   - Check journal configurations
   - Update documentation

### Database Cleanup

```python
# Clean old wizard records (automated by Odoo)
self.env['advance.settlement.wizard'].sudo().search([
    ('create_date', '<', fields.Datetime.now() - timedelta(days=7))
]).unlink()
```

---

## Extension Points

### Custom Scenarios

Add new settlement scenarios:

```python
# In settlement_wizard.py
scenario = fields.Selection([
    ('pay_employee', 'Pay Employee'),
    ('employee_refund', 'Employee Refund'),
    ('write_off', 'Write-off / Reclass'),
    ('transfer', 'Transfer to Another Account'),  # NEW
], ...)

# Add handler in _create_settlement_move()
elif self.scenario == 'transfer':
    # Custom journal entry logic
    ...
```

### Approval Workflow

Add approval requirement:

```python
# Add state field
state = fields.Selection([
    ('draft', 'Draft'),
    ('pending', 'Pending Approval'),
    ('approved', 'Approved'),
    ('done', 'Settled'),
], default='draft')

# Add approval method
def action_request_approval(self):
    self.state = 'pending'
    # Send notification
    
def action_approve(self):
    self.state = 'approved'
    return self.action_settle_advance()
```

### Multi-currency Support

Already supported! Settlement respects currency_id from advance box:

```python
# Lines automatically use correct currency
'currency_id': self.currency_id.id,
'amount_currency': self.target_amount,
```

---

## API Reference

### Public Methods

```python
action_settle_advance()
    """Main settlement action"""
    Args: None
    Returns: dict (ir.actions.act_window)
    Raises: UserError on validation failure

action_open_settlement_wizard()  # On advance.box
    """Open settlement wizard"""
    Args: None
    Returns: dict (ir.actions.act_window)
```

### Onchange Methods

```python
_onchange_box()
    """Update fields when box changes"""

_onchange_default_journal()
    """Auto-select journal for scenario"""

_onchange_amount_mode()
    """Reset amount when switching to full mode"""

_onchange_scenario()
    """Adjust fields based on scenario"""

_onchange_writeoff_policy()
    """Clear account when policy is none"""
```

### Compute Methods

```python
_compute_current_balance()
    """Get balance from advance box"""

_compute_target_amount()
    """Calculate settlement amount"""

_compute_direction()
    """Determine balance direction"""
```

### Constraint Methods

```python
_check_journal_required()
    """Validate journal selection"""

_check_amount_to_settle()
    """Validate partial amount"""

_check_writeoff_account()
    """Validate write-off account"""
```

---

## Changelog

### Version 17.0.1.0.4 (Current)

**Added:**
- Enhanced validation with scenario-balance matching
- Improved partner resolution with auto-creation
- Better error messages and user feedback
- Comprehensive logging for debugging
- Auto-reconciliation improvements

**Fixed:**
- Journal sequence handling
- Lock date validation with fallbacks
- Partner resolution for employees without partners
- Write-off scenario journal selection

**Improved:**
- UI with scenario descriptions and examples
- Validation messages with actionable guidance
- Error handling with detailed logs
- Documentation and help text

---

## References

### Related Models
- `employee.advance.box` - Main advance box model
- `account.move` - Journal entries
- `account.move.line` - Journal entry lines
- `account.journal` - Bank/Cash journals
- `res.partner` - Employee partners

### Related Views
- `view_employee_advance_box_form` - Advance box form with settlement button
- `view_advance_settlement_wizard_form` - Settlement wizard form

### Related Security
- `security/ir.model.access.csv` - Access rights

---

**Document Version:** 1.0
**Last Updated:** December 2024
**Module Version:** 17.0.1.0.4
**Odoo Version:** 17.0
