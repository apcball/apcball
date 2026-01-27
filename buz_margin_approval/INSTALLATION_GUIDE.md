# Installation & Testing Guide

## 📦 Installation Steps

### 1. Module Installation
```bash
# Restart Odoo server
sudo systemctl restart odoo

# Or if running manually
./odoo-bin -c odoo.conf

# Install module via Odoo UI
Apps → Search "buz_margin_approval" → Install
```

### 2. Update Existing Installation (if upgrading)
```bash
./odoo-bin -c odoo.conf -d your_database -u buz_margin_approval
```

---

## 👥 User Setup

### Step 1: Assign Groups

#### Sales Margin Approvers (Managers who can approve)
```
Settings → Users & Companies → Users
Select user → Access Rights tab
Add group: "Sales Margin Approvers"
```

#### Sales Margin Approver User (Sales users who must use Confirm To SO)
```
Settings → Users & Companies → Users
Select user → Access Rights tab
Add group: "Sales Margin Approver User"
```

---

## ⚙️ Configuration

### Step 2: Create Margin Approval Rules

```
Sales → Configuration → Margin Approval Rules → Create
```

#### Example Configuration:

**Rule: Sales Team A Margin Control**

**Tab: Sales Users**
- Add: John (Sales Person)
- Add: Mary (Sales Person)
- Add: Peter (Sales Person)

**Tab: Margin Lines**

| Min Margin | Max Margin | Approvers | Approval Type |
|------------|------------|-----------|---------------|
| 0% | 10% | Manager A, Manager B | Any |
| 10% | 15% | Team Lead C | Any |
| 15% | 20% | Director X, Director Y | All |

**Important Notes:**
- Users in "Sales Users" field will be subject to this rule
- "Approvers" in margin lines are those who can approve orders in that margin range
- "Any" = One approval is enough
- "All" = All approvers must approve

---

## 🧪 Testing Scenarios

### Test 1: Low Margin Order (Requires Approval - Type: Any)

**Setup:**
- Sales User: John (in rule)
- Margin: 8%
- Approvers: Manager A, Manager B (Type: Any)

**Steps:**
1. Login as John
2. Create quotation with 8% margin
3. Try to click "Confirm Sale" → Should get error
4. Click "Request Margin Approval"
5. Check: Manager A and Manager B receive email + activity
6. Login as Manager A
7. Sales → Margin Approvals → Open quotation
8. Click "Approve Margin"
9. Check: approval_state = 'approved'
10. Login as John
11. Click "Confirm To SO"
12. Check: confirm_flow_state = 'confirm_to_so'
13. Login as Admin (not in sales group)
14. Sales → Confirm To SO → Open order
15. Click "Confirm Sale"
16. Check: state = 'sale', confirm_flow_state = 'sale'

✅ **Expected Result:** Order successfully confirmed through proper flow

---

### Test 2: Low Margin Order (Requires Approval - Type: All)

**Setup:**
- Sales User: Mary (in rule)
- Margin: 18%
- Approvers: Director X, Director Y (Type: All)

**Steps:**
1. Login as Mary
2. Create quotation with 18% margin
3. Click "Request Margin Approval"
4. Login as Director X
5. Click "Approve Margin"
6. Check: approval_state still = 'pending' (need all approvers)
7. Check: Director X is in approved_user_ids
8. Login as Director Y
9. Click "Approve Margin"
10. Check: approval_state = 'approved' (all approved)
11. Login as Mary
12. Click "Confirm To SO"
13. Login as Admin
14. Click "Confirm Sale"

✅ **Expected Result:** Order requires all approvers before approval is complete

---

### Test 3: Rejection Flow

**Steps:**
1. Create quotation with low margin
2. Request approval
3. Approver clicks "Reject Margin"
4. Enter rejection reason: "Margin too low, please revise pricing"
5. Click "Confirm Rejection"
6. Check: approval_state = 'rejected'
7. Check: Rejection reason logged in chatter
8. Sales user tries "Confirm To SO" → Should get error
9. Sales user must revise order

✅ **Expected Result:** Order blocked until revised

---

### Test 4: Price Change Reset

**Steps:**
1. Create quotation with 8% margin
2. Request approval
3. Manager approves
4. Check: approval_state = 'approved'
5. Sales user changes product price or discount
6. Check: approval_state automatically resets to 'pending'
7. New activities created for approvers
8. Must request approval again

✅ **Expected Result:** Approval automatically resets on price/discount changes

---

### Test 5: Bypass Protection

**Steps:**
1. Login as Sales User (has group_sales_margin_approver_user)
2. Create quotation (margin doesn't matter)
3. DON'T click "Confirm To SO"
4. Try to click "Confirm Sale" directly
5. Should get error: "You must use 'Confirm To SO' button"

✅ **Expected Result:** Sales users cannot bypass Confirm To SO flow

---

### Test 6: Admin Direct Confirmation

**Steps:**
1. Login as Admin (does NOT have group_sales_margin_approver_user)
2. Create quotation
3. Click "Confirm Sale" directly
4. Check: Order confirmed successfully
5. Check: confirm_flow_state = 'sale'

✅ **Expected Result:** Admin can confirm orders directly without Confirm To SO

---

### Test 7: No Rule Needed

**Setup:**
- Sales User: Bob (NOT in any rule)
- OR margin is high (e.g., 25%)

**Steps:**
1. Create quotation
2. Check: No approval required (approval_state = 'not_required')
3. If user is in sales group: Click "Confirm To SO"
4. Admin clicks "Confirm Sale"

✅ **Expected Result:** Order flows normally without approval

---

## 📊 Verification Checklist

After installation, verify:

- ✅ Menu "Sales > Configuration > Margin Approval Rules" exists
- ✅ Menu "Sales > Orders > Margin Approvals" exists (for approvers)
- ✅ Menu "Sales > Orders > Confirm To SO" exists
- ✅ Can create margin approval rules
- ✅ Can add margin lines to rules
- ✅ Sale orders show margin_percentage field
- ✅ Sale orders show approval_state and confirm_flow_state
- ✅ Buttons appear/disappear based on state and user group
- ✅ Email notifications sent in Thai
- ✅ Mail activities created for approvers
- ✅ Chatter logs all approval actions

---

## 🐛 Troubleshooting

### Issue: Buttons not appearing
**Solution:** 
- Check user groups in Settings → Users
- Ensure user has correct Sales groups
- Refresh browser (Ctrl+F5)

### Issue: No approvers for margin range
**Solution:**
- Check margin approval rule configuration
- Ensure margin lines cover the order's margin percentage
- Add appropriate margin line for the range

### Issue: Cannot confirm after approval
**Solution:**
- If sales user: Use "Confirm To SO" button (not "Confirm Sale")
- Check approval_state = 'approved'
- Check no price changes after approval

### Issue: Email not sent
**Solution:**
- Check approver has email address
- Check Odoo outgoing mail server configured
- Check mail queue: Settings → Technical → Email → Emails

### Issue: User constraint error
**Solution:**
- A user can only be in one active rule per company
- Deactivate old rule or remove user from it

---

## 📈 Best Practices

1. **Rule Design**
   - Cover all possible margin ranges
   - Don't leave gaps between ranges
   - Start from 0% or negative values if needed

2. **Approver Assignment**
   - Use "Any" for faster approval
   - Use "All" for critical low-margin orders
   - Assign backup approvers

3. **User Training**
   - Train sales users on "Confirm To SO" flow
   - Train approvers to check margin carefully
   - Explain rejection and revision process

4. **Monitoring**
   - Regularly check "Margin Approvals" menu
   - Review rejected orders
   - Analyze margin trends

---

## 🔄 Workflow Summary

```
┌─────────────────────────────────────────────────────────────┐
│                     Sales User Creates SO                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
            ┌─────────────────┐
            │ Margin Check    │
            └────┬────────┬───┘
                 │        │
         Low     │        │    High/No Rule
                 │        │
                 ▼        ▼
    ┌────────────────┐  ┌──────────────────┐
    │ Request        │  │ No Approval      │
    │ Approval       │  │ Required         │
    └────┬───────────┘  └────┬─────────────┘
         │                   │
         ▼                   │
    ┌────────────────┐       │
    │ Approvers      │       │
    │ Review         │       │
    └────┬───────────┘       │
         │                   │
    ┌────▼────┬──────┐       │
    │ Approve │Reject│       │
    └────┬────┴───┬──┘       │
         │        │          │
         │    ┌───▼──────────┤
         │    │ Rejected     │
         │    │ (Must Revise)│
         │    └──────────────┘
         │
         ▼
    ┌────────────────┐
    │ Sales User:    │
    │ "Confirm To SO"│
    └────┬───────────┘
         │
         │◄──────────────────┘
         │
         ▼
    ┌────────────────┐
    │ Admin/Finance: │
    │ "Confirm Sale" │
    └────┬───────────┘
         │
         ▼
    ┌────────────────┐
    │ Sales Order    │
    │ (Confirmed)    │
    └────────────────┘
```

---

Generated: 2026-01-08
For: buz_margin_approval v2.0
