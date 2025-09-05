# Marketplace Settlement - Enhanced with Thai Localization

Enhanced Marketplace Settlement module for Odoo 17.0 with validation, security features, and comprehensive Thai localization integration.

## Overview

This module helps businesses manage marketplace settlements (e.g., Shopee, Lazada) by grouping multiple customer invoices into single settlement entries with automatic fee calculations, tax handling, and Thai withholding tax (WHT) integration.

## Enhanced Features

### 🔐 Validation & Security Features
- **Company Validation**: Ensures invoices belong to the current company
- **Duplicate Prevention**: Prevents settling already-settled invoices
- **Access Controls**: Role-based security with accounting groups
- **Audit Trail**: Complete tracking of settlement operations
- **Enhanced Error Handling**: Comprehensive validation with user-friendly messages

### 🇹🇭 Thai Localization Integration
- **WHT Certificate Generation**: Automatic integration with l10n_th_account_wht_cert_form
- **Thai Tax Calculations**: Integration with l10n_th_account_tax module
- **PND Form Support**: Support for PND1, PND2, PND3, PND3a, PND53
- **WHT Income Types**: Thai income type classification (40(1), 40(2), 40(3), 40(4)ก)
- **Profile-based Configuration**: Per-marketplace Thai tax settings
- **Conditional Loading**: Thai features only load when Thai modules are available

## Installation

### Base Installation
```bash
# Install the module
pip install -e /path/to/marketplace_settlement

# Update Odoo apps list
odoo-bin -u marketplace_settlement -d your_database
```

### Thai Localization Setup
```bash
# Install Thai localization modules (optional)
pip install odoo-addon-l10n-th-account-wht-cert-form
pip install odoo-addon-l10n-th-account-tax

# Update with Thai features
odoo-bin -u marketplace_settlement,l10n_th_account_wht_cert_form,l10n_th_account_tax -d your_database
```

## Configuration

### 1. Basic Setup
1. Go to **Accounting > Configuration > Marketplace > Profiles**
2. Create a new profile for each marketplace channel
3. Configure default partners, accounts, and tax rates

### 2. Thai Localization Setup
1. Open your marketplace profile
2. Go to the **Thai Localization** tab
3. Enable **Use Thai WHT**
4. Select appropriate **Income Tax Form** (e.g., PND3)
5. Choose **WHT Income Type** (e.g., "2. ค่าธรรมเนียม ค่านายหน้า")

### 3. Security Configuration
- Assign users to **Billing** or **Billing Administrator** groups
- Configure company-specific access as needed
- Review settlement audit logs regularly

## Usage

### Creating Settlements

1. **Navigate to Settlements**
   ```
   Accounting > Marketplace > Create Settlement
   ```

2. **Select Profile**
   - Choose pre-configured marketplace profile
   - Thai settings will be applied automatically if enabled

3. **Add Invoices**
   - Select customer invoices to settle
   - System validates company and settlement status
   - Preview calculations before confirmation

4. **Thai WHT Processing** (if enabled)
   - WHT certificates generated automatically
   - Thai tax forms updated
   - PND reports populated

### Managing Profiles

```python
# Example: Create Thai-enabled profile
profile = env['marketplace.settlement.profile'].create({
    'name': 'Shopee Thailand Profile',
    'trade_channel': 'shopee_th',
    'marketplace_partner_id': shopee_partner.id,
    'use_thai_wht': True,
    'thai_income_tax_form': 'pnd3',
    'thai_wht_income_type': '2',
    'default_vat_rate': 7.0,
    'default_wht_rate': 3.0,
})
```

## API Reference

### Models

#### `marketplace.settlement.profile`
Enhanced with Thai localization fields:
- `use_thai_wht`: Enable Thai WHT processing
- `thai_income_tax_form`: Default PND form
- `thai_wht_income_type`: Default WHT income type

#### `marketplace.settlement.wizard`
Enhanced settlement creation with:
- Company validation
- Duplicate prevention
- Thai WHT integration

#### `marketplace.settlement.thai.localization`
New model for Thai-specific features:
- WHT certificate management
- Thai tax integration
- PND form handling

### Security Groups
- `group_marketplace_settlement_user`: Basic settlement access
- `group_marketplace_settlement_manager`: Full settlement management

## Thai Localization Details

### PND Forms Supported
- **PND1**: Personal income tax
- **PND2**: Corporate income tax  
- **PND3**: Withholding tax (general)
- **PND3a**: Withholding tax (specific types)
- **PND53**: Special withholding tax

### WHT Income Types
- **1**: เงินเดือน ค่าจ้าง ฯลฯ 40(1) - Salary, wages
- **2**: ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2) - Fees, commissions  
- **3**: ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3) - Royalties
- **4A**: ดอกเบี้ย ฯลฯ 40(4)ก - Interest

### Integration Flow
```
Settlement Creation → Profile Check → Thai WHT Enabled? 
     ↓                                      ↓
Apply Thai Settings → Generate WHT Cert → Update Tax Reports
```

## Demo Data

The module includes comprehensive demo data:

### Thai Marketplace Partners
- Shopee (Thailand) Limited
- Lazada (Thailand) Co., Ltd.

### Pre-configured Profiles
- Shopee Thailand Profile (with WHT)
- Lazada Thailand Profile (with WHT)

### Test Scenarios
Load demo data to test:
```bash
odoo-bin -i marketplace_settlement --demo=all -d your_database
```

## Development

### File Structure
```
marketplace_settlement/
├── models/
│   ├── settlement.py          # Enhanced core settlement logic
│   ├── profile.py            # Enhanced profile with Thai fields
│   ├── thai_localization.py  # New Thai integration
│   └── __init__.py
├── views/
│   ├── marketplace_settlement_wizard_views.xml
│   ├── profile_views.xml     # Enhanced with Thai tab
│   ├── thai_localization_views.xml  # New Thai views
│   └── ...
├── data/
│   ├── thai_localization_demo.xml   # Thai demo data
│   └── ...
├── security/
│   ├── marketplace_settlement_security.xml  # Enhanced rules
│   └── ir.model.access.csv
└── thai_localization_test.py  # Test documentation
```

### Testing

Run tests to verify functionality:
```python
# Test Thai localization
python3 thai_localization_test.py

# Test Python syntax
python3 -m py_compile models/*.py

# Test XML syntax  
find views/ data/ -name "*.xml" -exec xmllint --noout {} \;
```

## Troubleshooting

### Common Issues

1. **Thai modules not found**
   ```
   Solution: Install l10n_th_account_wht_cert_form and l10n_th_account_tax
   ```

2. **Access denied errors**
   ```
   Solution: Assign users to appropriate accounting groups
   ```

3. **Company validation failures**
   ```
   Solution: Ensure invoices belong to current company
   ```

4. **Already settled invoices**
   ```
   Solution: System prevents duplicate settlements automatically
   ```

### Debug Mode
Enable debug mode to see detailed error messages:
```
Settings > Activate Developer Mode
```

## Support

For support and questions:
- Review the `thai_localization_test.py` file for usage examples
- Check Odoo logs for detailed error messages
- Verify Thai localization modules are properly installed
- Ensure proper security group assignments

## Changelog

### Version 17.0.1.0.0
- ✅ Enhanced with validation & security features
- ✅ Added comprehensive Thai localization integration
- ✅ Company validation and duplicate prevention
- ✅ Thai WHT certificate generation
- ✅ PND form support and WHT income type classification
- ✅ Profile-based Thai tax configuration
- ✅ Enhanced security with role-based access
- ✅ Complete audit trail and error handling
- ✅ Demo data for Thai marketplace scenarios

## License

LGPL-3 - See LICENSE file for details.