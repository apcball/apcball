# Settlement Feature - User Guide
## Employee Advance Module

### Overview
The Settlement feature allows you to properly close out employee advance boxes by creating appropriate accounting entries. This is essential for:
- Paying back employees for remaining advance balances
- Collecting overspent amounts from employees
- Writing off small discrepancies or special cases
- Maintaining accurate accounting records

---

## When to Use Settlement

### Common Scenarios:

1. **Employee Resignation/Termination**
   - Close out the advance box before final settlement
   - Either pay back the remaining balance or collect overspent amount

2. **End of Period/Fiscal Year**
   - Clean up advance boxes with zero balances
   - Reconcile any discrepancies

3. **Write-off Small Amounts**
   - Handle small discrepancies (e.g., rounding differences)
   - Forgive minor overspent amounts

4. **Account Reclassification**
   - Move balances to different accounts
   - Restructure accounting records

---

## Settlement Scenarios

### 1. Pay Employee (บริษัทจ่ายเงินให้พนักงาน)

**When to Use:**
- Employee has **positive balance** (company owes employee)
- Example: Employee has 5,000 THB remaining in advance box

**Accounting Entry:**
```
Dr 141101 (Employee Advance)    5,000 THB
   Cr Bank/Cash                      5,000 THB
```

**Process:**
1. Open advance box with positive balance
2. Click "Settle Advance" button
3. Select scenario: "Pay Employee"
4. Select Bank/Cash journal
5. Choose settlement date
6. Review and confirm
7. System creates journal entry and payment record

**Result:**
- Employee advance account (141101) is debited
- Bank/Cash account is credited
- Balance becomes zero (or reduced if partial)
- Employee receives payment

---

### 2. Employee Refund (พนักงานคืนเงินให้บริษัท)

**When to Use:**
- Employee has **negative balance** (employee owes company)
- Example: Employee overspent 2,000 THB

**Accounting Entry:**
```
Dr Bank/Cash                    2,000 THB
   Cr 141101 (Employee Advance)      2,000 THB
```

**Process:**
1. Open advance box with negative balance
2. Click "Settle Advance" button
3. Select scenario: "Employee Refund"
4. Select Bank/Cash journal
5. Choose settlement date
6. Collect cash/check from employee
7. Review and confirm
8. System creates journal entry

**Result:**
- Bank/Cash account is debited
- Employee advance account (141101) is credited
- Balance becomes zero (or reduced if partial)
- Company receives payment from employee

---

### 3. Write-off to Expense (ตัดจ่ายเป็นค่าใช้จ่าย)

**When to Use:**
- Small discrepancies or differences
- Company decides to absorb the cost
- Employee termination with forgiveness

**Accounting Entry:**
```
Dr Expense Account              500 THB
   Cr 141101 (Employee Advance)     500 THB
```

**Process:**
1. Open advance box
2. Click "Settle Advance" button
3. Select scenario: "Write-off/Reclass"
4. Select write-off policy: "Expense"
5. Select expense account (e.g., 6xxxx)
6. Enter reason in memo
7. Review and confirm

**Result:**
- Expense account is debited
- Employee advance account (141101) is credited
- Balance becomes zero
- No physical payment needed

---

### 4. Write-off to Other Income (ตัดรับเป็นรายได้อื่น)

**When to Use:**
- Employee returns more than expected
- Recovery of previously written-off amounts
- Gain from exchange rate differences

**Accounting Entry:**
```
Dr 141101 (Employee Advance)    300 THB
   Cr Other Income Account           300 THB
```

**Process:**
1. Open advance box
2. Click "Settle Advance" button
3. Select scenario: "Write-off/Reclass"
4. Select write-off policy: "Other Income"
5. Select income account (e.g., 4xxxx)
6. Enter reason in memo
7. Review and confirm

**Result:**
- Employee advance account (141101) is debited
- Other income account is credited
- Balance becomes zero
- Income is recognized

---

## Full vs Partial Settlement

### Full Settlement (เคลียร์ทั้งหมด)
- Settles the entire balance
- Closes the advance box
- Most common option

### Partial Settlement (เคลียร์บางส่วน)
- Settles only a portion of the balance
- Advance box remains open with reduced balance
- Useful for installment payments

**Example:**
```
Current Balance: 10,000 THB
Partial Settlement: 4,000 THB
Remaining Balance: 6,000 THB
```

---

## Step-by-Step Guide

### Method 1: From Advance Box

1. Navigate to: **Employee Advance → Advance Boxes**
2. Open the advance box you want to settle
3. Click **"Settle Advance"** button (visible only if balance ≠ 0)
4. Fill in the settlement wizard:
   - Review current balance
   - Select settlement scenario
   - Choose full or partial settlement
   - Select journal (for payment scenarios)
   - Set settlement date
5. Click **"Create Settlement"**
6. Review the created journal entry
7. Done!

### Method 2: From Settlement Menu

1. Navigate to: **Employee Advance → Settlement**
2. You'll see all advance boxes with non-zero balances
3. Open the advance box you want to settle
4. Follow steps 3-7 from Method 1

---

## Important Fields

### Settlement Date
- The accounting date for the journal entry
- Must not be in a locked fiscal period
- Defaults to today's date

### Journal
- Required for "Pay Employee" and "Employee Refund" scenarios
- Must be a Bank or Cash journal
- Used to record the payment transaction

### Amount Mode
- **Full Settlement:** Settles entire balance
- **Partial Settlement:** Settles specified amount

### Auto Reconcile
- Automatically reconciles 141101 lines
- Recommended: Keep enabled
- Matches debit/credit entries with same partner

### Activity
- Optional: Create follow-up activity
- Assign to user for tracking
- Add notes for reminders

---

## Validation & Safety Checks

The system performs these validations:

✅ **Balance Check:** Cannot settle if balance is zero

✅ **Lock Date:** Cannot post entries in locked periods

✅ **Journal Type:** Bank/Cash required for payment scenarios

✅ **Scenario Match:** Scenario must match balance direction
   - Pay Employee: Only for positive balance
   - Employee Refund: Only for negative balance

✅ **Partner Verification:** Employee must have partner configured

✅ **Account Configuration:** Advance box must have account 141101

✅ **Write-off Account:** Required when using write-off policy

---

## Error Messages & Solutions

### "Cannot settle advance box with zero balance"
**Solution:** No settlement needed. Balance is already zero.

### "You cannot add/modify entries prior to the lock date"
**Solution:** Choose a settlement date after the fiscal lock date.

### "Please select a Bank/Cash journal"
**Solution:** Select a journal with type "Bank" or "Cash".

### "Pay Employee scenario can only be used when company owes employee"
**Solution:** Check the balance. Use "Employee Refund" for negative balances.

### "Employee does not have a private partner configured"
**Solution:** Configure employee's private address in HR → Employees.

### "No general journal found for write-off entries"
**Solution:** Create a general journal first or use a different scenario.

---

## Best Practices

### 1. Document Everything
- Always fill in the memo field
- Explain the reason for settlement
- Include reference numbers if applicable

### 2. Review Before Posting
- Double-check the amount
- Verify the journal is correct
- Confirm the accounting date

### 3. Use Appropriate Scenarios
- Don't use write-off for normal payments
- Match scenario to actual transaction
- Follow company policy

### 4. Regular Reconciliation
- Enable auto-reconcile
- Review reconciled items monthly
- Clear unreconciled items promptly

### 5. Audit Trail
- Create follow-up activities for large amounts
- Attach supporting documents
- Maintain clear communication

---

## Example Workflows

### Example 1: Employee Resignation with Positive Balance

**Situation:**
- Employee: John Doe
- Resignation date: 31 Dec 2024
- Advance balance: 8,500 THB (positive)

**Steps:**
1. Open John Doe's advance box
2. Click "Settle Advance"
3. Select: "Pay Employee"
4. Journal: "Bank - Main"
5. Date: 31 Dec 2024
6. Memo: "Final settlement upon resignation"
7. Create Activity: Yes (for HR to verify)
8. Submit

**Result:**
- Journal entry created
- 8,500 THB paid to employee
- Advance box balance = 0
- HR notified for final processing

---

### Example 2: Overspent Recovery

**Situation:**
- Employee: Jane Smith
- Overspent: 1,200 THB (negative balance)
- Monthly installment: 400 THB

**Steps:**
1. Open Jane Smith's advance box
2. Click "Settle Advance"
3. Select: "Employee Refund"
4. Amount Mode: "Partial Settlement"
5. Amount: 400 THB
6. Journal: "Cash"
7. Memo: "Month 1/3 installment"
8. Submit

**Result:**
- 400 THB received from employee
- Remaining balance: -800 THB
- Will settle in 2 more months

---

### Example 3: Small Difference Write-off

**Situation:**
- Employee: Bob Wilson
- Balance: 15.50 THB (rounding difference)
- Company policy: Write-off < 50 THB

**Steps:**
1. Open Bob Wilson's advance box
2. Click "Settle Advance"
3. Select: "Write-off/Reclass"
4. Policy: "Expense"
5. Account: "Other Expenses - Miscellaneous"
6. Memo: "Rounding difference write-off"
7. Submit

**Result:**
- 15.50 THB written off to expense
- Advance box balance = 0
- No payment needed

---

## Troubleshooting

### Settlement button not visible?
- Check if balance is zero
- Refresh the page
- Verify user permissions

### Journal entry not created?
- Check error message
- Verify all required fields
- Check journal sequence configuration

### Reconciliation not working?
- Verify partner matches
- Check if lines are already reconciled
- Ensure account matches (141101)

### Balance not updated?
- Wait a few seconds and refresh
- Check if entry was posted
- Verify balance computation

---

## Technical Notes

### Accounting Entries by Scenario

**Pay Employee:**
```
Account 141101 (Employee)    Dr
Bank/Cash Account            Cr
```

**Employee Refund:**
```
Bank/Cash Account            Dr
Account 141101 (Employee)    Cr
```

**Write-off to Expense:**
```
Expense Account              Dr
Account 141101 (Employee)    Cr
```

**Write-off to Other Income:**
```
Account 141101 (Employee)    Dr
Other Income Account         Cr
```

### Auto Reconciliation Logic
1. Finds all unreconciled 141101 lines with same partner
2. Separates debit and credit lines
3. Matches debit vs credit by amount
4. Creates reconciliation record
5. Marks lines as reconciled

---

## FAQ

**Q: Can I edit a settlement after posting?**
A: No. Once posted, you must reverse the entry and create a new one.

**Q: What if I chose the wrong scenario?**
A: Reverse the journal entry and create a new settlement with correct scenario.

**Q: Can I settle multiple employees at once?**
A: No. Each advance box must be settled individually for proper audit trail.

**Q: Is approval required for settlement?**
A: Depends on your company policy. Configure in module settings.

**Q: What happens to the advance box after settlement?**
A: It remains open but with zero balance. You can refill it later.

**Q: Can I settle in foreign currency?**
A: Yes, if the advance box uses foreign currency.

**Q: How do I track settlement history?**
A: Check the chatter/messages on the advance box for audit trail.

---

## Related Features

- **Refill Advance Box:** Add money to advance box
- **Clear Advance:** Create vendor bills from expenses
- **Expense Sheet:** Submit and approve expenses
- **WHT Integration:** Handle withholding tax

---

## Support

For technical issues or questions:
1. Check error messages carefully
2. Review this guide
3. Contact system administrator
4. Check module logs for details

---

**Last Updated:** December 2024
**Module Version:** 17.0.1.0.4
**Author:** Your Company
