# Trade Channel Profiles Enhancement

## Overview

This enhancement extends the marketplace_settlement module with **Trade Channel Profiles** that define default configurations for each marketplace platform (Shopee, Lazada, TikTok, SPX). This provides centralized management of vendor and customer settings, making marketplace operations more automated and consistent.

## Features

### Trade Channel Configuration

Each profile defines comprehensive settings for a specific marketplace:

#### Settlement Configuration (Customer Side)
- **Marketplace Partner**: Default customer partner for settlements
- **Sales Journal**: Default journal for customer settlements
- **Settlement Account**: Default receivable account for settlements

#### Vendor Bill Configuration (Vendor Side)
- **Vendor Partner**: Default vendor partner for marketplace fees
- **Purchase Journal**: Default journal for vendor bills
- **Default Tax Rates**: VAT and WHT percentages
- **Tax Records**: Linked VAT and WHT tax records
- **Expense Accounts**: Pre-configured accounts for different fee types

#### Document Patterns
- **Invoice Pattern**: Pattern for tax invoices (e.g., "TR" for Shopee)
- **Receipt Pattern**: Pattern for receipts (e.g., "RC" for SPX)

### Supported Trade Channels

#### 1. Shopee Thailand
- **Invoice Pattern**: TR (Tax Invoice)
- **Default Tax Rates**: 7% VAT + 3% WHT
- **Expense Categories**:
  - Platform Commission (6201)
  - Service Fees (6202)
  - Advertising Fees (6203)

#### 2. SPX Technologies
- **Receipt Pattern**: RC (Receipt)
- **Default Tax Rates**: 0% VAT + 1% WHT
- **Expense Categories**:
  - Logistics Fees (6204)
  - Shipping Charges (6205)

#### 3. Lazada Thailand
- **Invoice Pattern**: LZ
- **Default Tax Rates**: 7% VAT + 3% WHT
- **Similar structure to Shopee**

#### 4. TikTok Shop Thailand
- **Invoice Pattern**: TT
- **Default Tax Rates**: 7% VAT + 3% WHT
- **Similar structure to Shopee**

## Profile Integration

### Automatic Profile Detection

1. **By Document Type**: When creating vendor bills, profiles are auto-selected based on document type
2. **By Document Pattern**: Document references (TR*, RC*, etc.) automatically map to profiles
3. **Manual Selection**: Users can manually override profile selection

### Default Value Application

When a profile is selected:
- **Partner**: Auto-fills vendor partner
- **Journal**: Sets default purchase journal
- **Tax Rates**: Applies default VAT/WHT percentages
- **Accounts**: Pre-populates expense accounts
- **Line Items**: Creates default line structure

### Profile-Based Line Creation

Profiles automatically generate appropriate line items:

**Shopee Profile** creates:
- Platform Commission line
- Service Fees line
- Advertising Fees line

**SPX Profile** creates:
- Logistics Fees line
- Shipping Charges line

## Configuration Management

### Creating Profiles

1. **Navigate**: Accounting → Configuration → Profiles
2. **Create New**: Click "Create" 
3. **Basic Info**:
   - Name (e.g., "Shopee Thailand Profile")
   - Trade Channel selection
   - Document patterns
4. **Settlement Configuration**:
   - Marketplace partner for customer settlements
   - Sales journal and accounts
5. **Vendor Configuration**:
   - Vendor partner for fees
   - Purchase journal
   - Default tax rates and tax records
   - Expense account mapping

### Profile Management

- **Active/Inactive**: Profiles can be activated/deactivated
- **Company-Specific**: Support for multi-company environments
- **Notes**: Additional configuration documentation
- **Audit Trail**: Full change tracking

## Enhanced Workflows

### Vendor Bill Creation

1. **Import Documents**: Select document type
2. **Auto-Profile Selection**: System selects appropriate profile
3. **Default Population**: All fields populated from profile
4. **Manual Override**: Users can modify as needed
5. **Line Generation**: Default lines created based on profile

### CSV Import

Profiles enhance CSV import by:
- **Auto-Detection**: Document patterns map to profiles
- **Default Values**: Missing data filled from profiles
- **Consistency**: Ensures uniform processing across batches

## API Methods

### Profile Model Methods

```python
# Get profile by trade channel
profile = env['marketplace.settlement.profile'].get_profile_by_channel('shopee')

# Get profile by document pattern
profile = env['marketplace.settlement.profile'].get_profile_by_document_pattern('TR2024001')

# Get default account for expense type
account = profile.get_default_account_for_type('commission')

# Get line configuration
config = profile.get_default_line_config('service')
```

### Integration Methods

Vendor bill model automatically uses profiles for:
- Partner selection
- Journal configuration
- Tax rate application
- Account mapping
- Line item creation

## Database Structure

### New Profile Fields

```sql
-- Settlement Configuration
marketplace_partner_id      -- Customer partner
journal_id                 -- Sales journal
settlement_account_id      -- Receivable account

-- Vendor Configuration  
vendor_partner_id          -- Vendor partner
purchase_journal_id        -- Purchase journal
default_vat_rate          -- Default VAT %
default_wht_rate          -- Default WHT %
vat_tax_id                -- VAT tax record
wht_tax_id                -- WHT tax record

-- Expense Accounts
commission_account_id      -- Commission expense
service_fee_account_id     -- Service fee expense
advertising_account_id     -- Advertising expense
logistics_account_id       -- Logistics expense
other_expense_account_id   -- Other expenses

-- Document Patterns
invoice_pattern           -- Tax invoice pattern
receipt_pattern          -- Receipt pattern

-- Metadata
active                   -- Active flag
company_id              -- Company
notes                   -- Configuration notes
```

## Demo Data

The module includes comprehensive demo data:

### Partners
- Shopee Thailand (Customer/Vendor)
- SPX Technologies (Vendor)
- Lazada Thailand (Customer/Vendor)
- TikTok Shop Thailand (Customer/Vendor)

### Profiles
- Complete Shopee profile with all configurations
- SPX logistics profile
- Lazada marketplace profile
- TikTok Shop profile

### Accounts
- 6201: Marketplace Commission
- 6202: Service Fees
- 6203: Advertising Expense
- 6204: Logistics Expense
- 6205: Shipping Expense

### Taxes
- VAT Purchase 7%
- WHT Purchase 3%
- WHT Purchase 1%

## Benefits

### Operational Efficiency
- **Automated Setup**: Reduces manual configuration per document
- **Consistency**: Ensures uniform processing across channels
- **Speed**: Faster document creation with pre-filled defaults

### Compliance
- **Tax Accuracy**: Correct VAT/WHT rates per channel
- **Account Mapping**: Proper expense categorization
- **Audit Trail**: Complete configuration tracking

### Maintenance
- **Centralized Config**: Single source of truth per channel
- **Easy Updates**: Change rates/accounts in one place
- **Scalability**: Easy addition of new channels

### User Experience
- **Intuitive**: Logical flow from channel to configuration
- **Flexible**: Override defaults when needed
- **Guided**: Clear structure for document processing

This enhancement transforms marketplace processing from manual configuration to automated, profile-driven workflows that ensure consistency, compliance, and efficiency across all trade channels.
