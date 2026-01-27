# Quick Installation Guide

## Module: internal_consume_request

### Status: ✅ Ready to Install

## Installation Steps

### 1. Module is already in place
```bash
/opt/instance1/odoo17/custom-addons/internal_consume_request/
```

### 2. Restart Odoo Service
```bash
sudo systemctl restart instance1
```

### 3. Update Apps List
- Open Odoo in browser
- Go to: **Apps**
- Click: **Update Apps List** (top-right menu)
- Confirm the update

### 4. Install Module
- In Apps menu, remove "Apps" filter
- Search: **"Internal Consumable Request"** or **"internal_consume_request"**
- Click **Install**

### 5. Assign User Groups
Go to: **Settings → Users & Companies → Users**

For each user, assign appropriate groups:
- **Regular Employees**: Internal Consume / User
- **Team Managers**: Internal Consume / Manager  
- **Stock Personnel**: Internal Consume / Stock User

## Verify Installation

### Check Menu Access
After installation, you should see:
1. **Main Menu**: Internal Consume → Requests
2. **Alternative**: Inventory → Internal Consume Requests

### Test Basic Flow
1. **As Employee**:
   - Create new request
   - Add products (check available qty)
   - Submit for approval

2. **As Manager**:
   - Check "To Approve" menu or mail activities
   - Approve request
   - Verify picking is created

3. **As Stock User**:
   - View picking via smart button
   - Validate transfer
   - Mark request as Done

## Configuration (Optional)

### Default Warehouse
If warehouse code is NOT "ST02":
1. Go to: Inventory → Configuration → Warehouses
2. Find your warehouse
3. Note the code
4. Update code in: `models/internal_consume_request.py`
   ```python
   warehouse = self.env['stock.warehouse'].search([
       ('code', '=', 'YOUR_CODE')  # Change here
   ], limit=1)
   ```

### Default Locations
Adjust source/destination locations in same file if needed.

## Troubleshooting

### Module not appearing in Apps
- Ensure you clicked "Update Apps List"
- Check Odoo logs: `sudo journalctl -u instance1 -f`

### Permission Errors
- Verify user has correct group assigned
- Check: Settings → Users → [User] → Access Rights tab

### Picking not created
- Check warehouse and picking type configuration
- Ensure locations exist and are type "Internal"
- Check Odoo server logs for errors

## Support
For issues or questions, check:
- README.md (module overview)
- IMPLEMENTATION.md (technical details)
- Odoo logs: `sudo journalctl -u instance1 -f`

---
**Module Path**: `/opt/instance1/odoo17/custom-addons/internal_consume_request/`
**Ready for Production**: ✅ Yes
