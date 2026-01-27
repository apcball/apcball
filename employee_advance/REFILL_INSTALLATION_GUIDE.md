# Quick Installation Guide - Refill Advance Box Feature

## 🔧 Installation Steps

### 1. Upgrade the Module

```bash
# Navigate to Odoo directory
cd /opt/instance1/odoo17

# Upgrade the module
./odoo-bin -c odoo.conf -u employee_advance -d your_database_name --stop-after-init
```

Or from Odoo interface:
1. Go to **Apps**
2. Remove "Apps" filter
3. Search for "Employee Advance"
4. Click **Upgrade**

### 2. Verify Installation

After upgrade, check that:

✅ **Models are loaded:**
- `advance.box.refill` 
- `wizard.refill.advance.box`

✅ **Menus appear:**
- Accounting → Advance Box → Refill History
- Accounting → Advance Box → New Refill

✅ **Views are accessible:**
- Can open Refill History list
- Can create new refill via wizard
- Smart buttons appear on Advance Box form

### 3. Initial Configuration

#### For Each Advance Box:

1. Navigate to **Accounting → Advance Box → Advance Boxes**
2. Open an advance box
3. Ensure these fields are set:
   - **Journal** (type: cash or bank) - Required for refills
   - **Account** - Required for balance calculation
   - **Employee** - Required
   - **Base Amount** (optional) - For "Refill to Base" feature

#### Setup Bank Journals:

1. Go to **Accounting → Configuration → Journals**
2. Verify bank journals are configured with:
   - Type = Bank
   - Default Debit/Credit Accounts set
   - Currency configured if multi-currency

## 🧪 Test the Feature

### Test Case 1: Basic Refill

1. Go to **Accounting → Advance Box → New Refill**
2. Select an advance box
3. Select a bank journal
4. Enter amount: 5000
5. Click **Confirm Refill**
6. ✅ Should show success message
7. ✅ Payment should be created and posted
8. ✅ Balance should update on advance box

### Test Case 2: View History

1. Open an advance box
2. Click **Refills** smart button (shows count)
3. ✅ Should see list of all refills
4. ✅ Click on a refill to see details
5. ✅ Click "View Payment" button to see the payment

### Test Case 3: Check Accounting

1. From refill record, click "View Payment"
2. From payment, click "Journal Items"
3. ✅ Verify entries:
   ```
   Dr: Advance Box Account  5,000.00
       Cr: Bank Account           5,000.00
   ```

### Test Case 4: From Advance Box Form

1. Open an advance box
2. Click **New Refill** button
3. ✅ Wizard opens with box pre-selected
4. Complete and confirm
5. ✅ Refill count increments

## 🔍 Troubleshooting

### Issue: Menu not appearing
**Solution:** Clear cache and reload
```bash
# Restart Odoo service
sudo systemctl restart odoo17
```

### Issue: Access denied
**Solution:** Check user groups
- Users need `account.group_account_user` to create refills
- OR `base.group_erp_manager` for full access

### Issue: Journal not showing in wizard
**Solution:** 
- Ensure journal type = 'bank'
- Check journal is active
- Verify user has access to journal's company

### Issue: Balance not updating
**Solution:**
- Ensure advance box has `journal_id` set
- Journal must have `default_account_id` configured
- Try manual recompute:
  ```python
  # From Odoo shell
  boxes = env['employee.advance.box'].search([])
  boxes._compute_balance()
  ```

### Issue: Payment not posting
**Solution:**
- Check bank journal configuration
- Ensure both journals have accounts configured
- Check for account locks or period closures
- Verify sufficient permissions

## 📊 Database Changes

The upgrade will create these new database tables:
- `advance_box_refill` - Stores refill history
- `wizard_refill_advance_box` - Transient wizard data

And add these columns to existing tables:
- `employee_advance_box.refill_count` (computed, not stored)

## 🎯 User Permissions

| Action | Required Group |
|--------|---------------|
| View refills | `base.group_user` |
| Create refills | `account.group_account_user` or `account.group_account_manager` |
| Edit refills | `account.group_account_user` or `account.group_account_manager` |
| Delete refills | `account.group_account_manager` only |

## ✅ Post-Installation Checklist

- [ ] Module upgraded successfully
- [ ] All menus visible
- [ ] Access rights working correctly
- [ ] Can create refill from wizard
- [ ] Payment is created and posted
- [ ] Balance updates correctly
- [ ] Refill history displays properly
- [ ] Smart buttons work on advance box
- [ ] Multi-company filtering works (if applicable)
- [ ] Multi-currency works (if applicable)

## 🚀 Ready to Use!

Once all checks pass, the feature is ready for production use.

For detailed documentation, see: `REFILL_FEATURE_IMPLEMENTATION.md`
