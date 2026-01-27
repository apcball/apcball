# Installation & Deployment Checklist

## Pre-Installation

- [ ] Verify Odoo 17 Community Edition is running
- [ ] Backup current database
- [ ] Ensure required modules are installed:
  - [ ] sale
  - [ ] stock
  - [ ] account
  - [ ] mail
- [ ] Verify user has admin privileges

## Installation Steps

### 1. Module Deployment
- [ ] Copy module to addons directory: `/opt/instance1/odoo17/custom-addons/`
- [ ] Verify file permissions are correct
- [ ] Restart Odoo service: `sudo systemctl restart odoo`
- [ ] Check Odoo log for errors: `sudo journalctl -u odoo -f`

### 2. Module Installation
- [ ] Login to Odoo as administrator
- [ ] Go to **Apps** menu
- [ ] Click **Update Apps List**
- [ ] Remove "Apps" filter
- [ ] Search for "Warranty Management" or "buz_warranty_management"
- [ ] Click **Install** button
- [ ] Wait for installation to complete
- [ ] Verify no error messages appear

### 3. Post-Installation Verification
- [ ] New menu "Warranty" appears in main menu bar
- [ ] Submenu "Warranty Cards" accessible
- [ ] Submenu "Warranty Claims" accessible
- [ ] No console errors in browser

## Configuration Steps

### 4. User Access Setup
- [ ] Go to **Settings > Users & Companies > Users**
- [ ] For service desk staff:
  - [ ] Edit user
  - [ ] Add to group: **Warranty / User**
  - [ ] Save
- [ ] For managers:
  - [ ] Edit user
  - [ ] Add to group: **Warranty / Manager**
  - [ ] Save
- [ ] Test access by logging in as different users

### 5. Product Configuration
- [ ] Go to **Inventory > Products > Products**
- [ ] Select a test product
- [ ] Navigate to **Warranty Information** tab
- [ ] Verify all fields are visible:
  - [ ] Auto Create Warranty checkbox
  - [ ] Warranty Duration field
  - [ ] Warranty Type dropdown
  - [ ] Allow Out-of-Warranty checkbox
  - [ ] Service Product selector
  - [ ] Warranty Terms text area
- [ ] Configure test product:
  - [ ] Enable Auto Create Warranty
  - [ ] Set Duration to 12 months
  - [ ] Select Type: Repair
  - [ ] Enter sample terms
  - [ ] Save product

### 6. Service Product Setup (Optional)
- [ ] Create new product for out-of-warranty service:
  - [ ] Name: "Warranty Repair Service"
  - [ ] Type: Service
  - [ ] Set price (e.g., $50/hour)
  - [ ] Save
- [ ] Link service product to warranty products
- [ ] Verify service product appears in wizard

## Functional Testing

### 7. Test Automatic Warranty Creation
- [ ] Create new sale order
- [ ] Add warranty-enabled product
- [ ] Confirm sale order
- [ ] Create delivery
- [ ] Validate delivery (mark as Done)
- [ ] Go to **Warranty > Warranty Cards**
- [ ] Verify new warranty card created:
  - [ ] Correct warranty number (WARR/YYYY/####)
  - [ ] Status is "Active"
  - [ ] Start date matches delivery date
  - [ ] End date is start date + duration
  - [ ] Customer info correct
  - [ ] Product info correct
  - [ ] Linked to sale order
  - [ ] Linked to delivery

### 8. Test Warranty Certificate
- [ ] Open warranty card from test
- [ ] Click **Print Certificate** button
- [ ] Verify PDF generates
- [ ] Check certificate contents:
  - [ ] Company logo/header appears
  - [ ] Warranty number displayed
  - [ ] Customer information correct
  - [ ] Product details correct
  - [ ] Warranty dates correct
  - [ ] Terms and conditions shown
  - [ ] Signature blocks present
- [ ] Save/download PDF successfully

### 9. Test Under-Warranty Claim Flow
- [ ] Go to **Warranty > Warranty Claims**
- [ ] Click **Create**
- [ ] Select warranty card from test
- [ ] Verify auto-filled data:
  - [ ] Customer pre-filled
  - [ ] Product pre-filled
  - [ ] Serial/lot pre-filled
- [ ] Enter problem description
- [ ] Select claim type (Repair)
- [ ] Save claim
- [ ] Verify green "Under Warranty" badge shows
- [ ] Click **Under Review** button
- [ ] Add internal notes
- [ ] Click **Approve** button
- [ ] Enter resolution details
- [ ] Click **Mark as Done** button
- [ ] Verify status updates correctly

### 10. Test Claim Form Report
- [ ] Open claim from test
- [ ] Click **Print Claim Form** button
- [ ] Verify PDF generates
- [ ] Check form contents:
  - [ ] Claim number displayed
  - [ ] Customer info correct
  - [ ] Product info correct
  - [ ] Warranty info correct
  - [ ] Problem description shown
  - [ ] Internal notes shown (if any)
  - [ ] Resolution shown
  - [ ] Signature blocks present
- [ ] Save/download PDF successfully

### 11. Test Out-of-Warranty Flow
- [ ] Create expired warranty (manual):
  - [ ] Create warranty card manually
  - [ ] Set end date to past date
  - [ ] Save and activate
- [ ] Create claim on expired warranty
- [ ] Verify red "Out of Warranty" warning shows
- [ ] Verify warranty end date displays
- [ ] Enter cost estimate
- [ ] Click **Create Quotation** button
- [ ] Wizard opens with:
  - [ ] Claim auto-filled
  - [ ] Customer auto-filled
  - [ ] Service product auto-filled (if configured)
  - [ ] Cost pre-filled from estimate
- [ ] Adjust cost if needed
- [ ] Add description
- [ ] Click **Create Quotation**
- [ ] Verify redirected to sale order
- [ ] Check sale order:
  - [ ] Customer correct
  - [ ] Service product added
  - [ ] Price correct
  - [ ] Description includes claim number
- [ ] Return to claim
- [ ] Verify quotation linked
- [ ] Click **View Quotation** button works

### 12. Test Filters and Search
- [ ] **Warranty Cards:**
  - [ ] Test "Active" filter
  - [ ] Test "Expired" filter
  - [ ] Test "Near Expiry" filter
  - [ ] Test search by customer
  - [ ] Test search by product
  - [ ] Test grouping by customer
  - [ ] Test grouping by product
- [ ] **Warranty Claims:**
  - [ ] Test "Under Warranty" filter
  - [ ] Test "Out of Warranty" filter
  - [ ] Test status filters
  - [ ] Test search functionality
  - [ ] Test grouping options

### 13. Test Smart Buttons
- [ ] Go to product with warranties
- [ ] Verify **Warranties** smart button shows count
- [ ] Click button, verify filter works
- [ ] Go to warranty card with claims
- [ ] Verify **Claims** smart button shows count
- [ ] Click button, verify filter works

### 14. Test Chatter Functionality
- [ ] Open warranty card
- [ ] Send message in chatter
- [ ] Add follower
- [ ] Schedule activity
- [ ] Log note
- [ ] Verify all chatter features work
- [ ] Repeat for warranty claim

### 15. Test Scheduled Action
- [ ] Go to **Settings > Technical > Automation > Scheduled Actions**
- [ ] Search for "Warranty: Update Expired Status"
- [ ] Verify action exists and is active
- [ ] Note: To test immediately:
  - [ ] Click **Run Manually** button
  - [ ] Check that expired warranties update to "Expired" status

## Security Testing

### 16. Test User Permissions
- [ ] Login as **Warranty User**:
  - [ ] Can view warranty cards
  - [ ] Cannot create warranty cards manually
  - [ ] Cannot delete warranty cards
  - [ ] Can create claims
  - [ ] Can edit claims
  - [ ] Cannot delete claims
- [ ] Login as **Warranty Manager**:
  - [ ] Can view warranty cards
  - [ ] Can create warranty cards
  - [ ] Can edit warranty cards
  - [ ] Can delete warranty cards
  - [ ] Can create claims
  - [ ] Can edit claims
  - [ ] Can delete claims

### 17. Test Record Rules
- [ ] Verify users can only see appropriate records
- [ ] Test multi-company if applicable
- [ ] Verify no unauthorized access possible

## Performance Testing

### 18. Test with Volume
- [ ] Create multiple warranties (10+)
- [ ] Create multiple claims (10+)
- [ ] Test list view load times
- [ ] Test search/filter performance
- [ ] Test report generation speed
- [ ] Verify no timeout errors

## Integration Testing

### 19. Sales Integration
- [ ] Verify warranty links to sale orders
- [ ] Test with different sale workflows
- [ ] Verify quotation creation from claims

### 20. Stock Integration
- [ ] Test with different delivery types
- [ ] Test with serial numbers
- [ ] Test with lot numbers
- [ ] Verify picking links work

### 21. Accounting Integration
- [ ] Verify out-of-warranty quotations create invoices
- [ ] Test payment processing
- [ ] Verify accounting entries

## Documentation Review

### 22. Verify Documentation
- [ ] README.md is clear and accurate
- [ ] IMPLEMENTATION_GUIDE.md covers all scenarios
- [ ] QUICKSTART.md provides fast onboarding
- [ ] INSTALLATION_CHECKLIST.md (this file) is complete

## Rollout Preparation

### 23. Training Materials
- [ ] Prepare user training slides
- [ ] Create quick reference guide
- [ ] Record demo videos (optional)
- [ ] Schedule training sessions

### 24. Communication Plan
- [ ] Notify users of new feature
- [ ] Provide access to documentation
- [ ] Set up support channel
- [ ] Schedule go-live date

### 25. Backup & Rollback Plan
- [ ] Document current database state
- [ ] Create backup before go-live
- [ ] Prepare rollback procedure
- [ ] Test backup restoration

## Go-Live

### 26. Production Deployment
- [ ] Deploy during low-traffic period
- [ ] Monitor for errors
- [ ] Check log files
- [ ] Verify all features working
- [ ] Test with real users

### 27. Post-Go-Live
- [ ] Monitor usage for first week
- [ ] Collect user feedback
- [ ] Address any issues promptly
- [ ] Document lessons learned
- [ ] Plan enhancements

## Ongoing Maintenance

### 28. Regular Tasks
- [ ] Review warranty expiry reports weekly
- [ ] Monitor claim processing times
- [ ] Update warranty terms as needed
- [ ] Review and update service pricing
- [ ] Check scheduled action runs daily

### 29. Monthly Review
- [ ] Generate warranty statistics
- [ ] Review claim resolution rates
- [ ] Analyze out-of-warranty revenue
- [ ] Identify improvement opportunities
- [ ] Update documentation if needed

## Troubleshooting

### Common Issues & Solutions

#### Issue: Module won't install
- [ ] Check Odoo logs for errors
- [ ] Verify Python syntax: `python3 -m py_compile *.py`
- [ ] Check XML syntax in views
- [ ] Verify dependencies installed

#### Issue: Warranty not auto-creating
- [ ] Verify product has `auto_warranty = True`
- [ ] Check warranty duration > 0
- [ ] Confirm delivery is validated (Done state)
- [ ] Check Odoo logs for errors

#### Issue: Can't create out-of-warranty quotation
- [ ] Verify `allow_out_of_warranty = True` on product
- [ ] Check warranty is actually expired
- [ ] Verify service product configured
- [ ] Check user has correct permissions

#### Issue: Reports not generating
- [ ] Check report template names match
- [ ] Verify QWeb syntax is correct
- [ ] Check for missing fields
- [ ] Review Odoo logs

#### Issue: Access denied errors
- [ ] Verify user in correct group
- [ ] Check security rules
- [ ] Review ir.model.access.csv
- [ ] Check record rules in security.xml

## Sign-Off

### Completed By
- **Name:** _____________________
- **Date:** _____________________
- **Signature:** _____________________

### Approved By
- **Name:** _____________________
- **Date:** _____________________
- **Signature:** _____________________

---

## Status: 
- [ ] **All checks passed - Ready for production**
- [ ] **Issues found - Requires attention**
- [ ] **In progress - Testing continues**

---

**Notes:**
_Use this space to document any issues, observations, or special configurations:_

_______________________________________________
_______________________________________________
_______________________________________________
_______________________________________________
