# Marketplace Settlement - Fee Allocation Feature

## Overview

The Fee Allocation feature enables detailed distribution of marketplace fees, VAT, and withholding tax across individual invoices for comprehensive profitability analysis and reporting. This functionality is designed specifically for reporting purposes and has **no General Ledger (GL) impact**.

## Key Features

### 1. Fee Allocation Model (`marketplace.fee.allocation`)

- **Purpose**: Store distributed fee values per invoice for reporting and profitability analysis
- **Linked Data**: Connected to Settlement and Invoice records
- **Allocation Methods**:
  - **Proportional**: Distribute fees based on pre-tax sales amount per invoice
  - **Exact**: Use specific values provided by marketplace CSV files (Shopee, Lazada, etc.)

### 2. Stored Allocation Values

Each allocation record stores:
- `base_fee_alloc`: Marketplace commission/fee allocated to this invoice
- `vat_input_alloc`: VAT on marketplace fee allocated to this invoice  
- `wht_alloc`: Withholding tax allocated to this invoice
- `net_payout_alloc`: Net amount after deductions allocated to this invoice

### 3. Allocation Methods

#### Proportional Allocation
- Automatically distributes settlement fees based on each invoice's pre-tax amount
- Formula: `(Invoice Pre-tax Amount / Total Settlement Pre-tax Amount) * Settlement Fee`
- Ideal for settlements where marketplace doesn't provide detailed breakdown

#### Exact Allocation
- Uses specific values from marketplace payout CSV files
- Perfect for Shopee, Lazada, TikTok payout reports that include fee breakdowns
- Supports CSV import wizard for bulk processing

## Usage Guide

### 1. Generate Fee Allocations

From a Settlement record:
1. Navigate to the **Fee Allocations** tab
2. Set the **Default Allocation Method** (Proportional or Exact)
3. Click **Generate Allocations** to create allocation records for all invoices
4. For proportional method, allocations are calculated automatically
5. For exact method, use CSV import or manual entry

### 2. Import from CSV (Exact Method)

For marketplace payout CSV files:
1. Click **Import from CSV** button
2. Upload your marketplace payout CSV file
3. Map columns (Invoice Number, Base Fee, VAT Input, WHT)
4. Preview and import data
5. Review imported allocations

### 3. CSV Import Features

- **Flexible Format**: Supports various delimiters (comma, semicolon, tab, pipe)
- **Column Mapping**: Customize which columns contain which data
- **Preview Function**: See how data will be imported before processing
- **Template Download**: Generate CSV template with settlement invoices
- **Update Mode**: Replace existing allocations or update specific values
- **Validation**: Ensures invoices exist in settlement and validates amounts

### 4. Reporting and Analysis

#### Fee Allocation Records
- **Menu**: Accounting → Receivables → Fee Allocations
- **Views**: Tree, Form, Pivot, Graph views available
- **Features**: Filter by allocation method, settlement, customer, time period

#### Fee Allocation Analysis Report
- **Menu**: Accounting → Reports → Fee Allocation Analysis  
- **Purpose**: Advanced reporting with profitability metrics
- **Metrics**: 
  - Gross Profit (Revenue - Allocated Fees)
  - Profit Margin % 
  - Fee breakdown by customer/channel
  - Time-based trend analysis

### 5. Integration with Settlement Workflow

Fee allocations integrate seamlessly with existing settlement features:
- **Settlement Creation**: Generate allocations after posting settlement
- **AR/AP Netting**: Fee allocations remain for reporting even after netting
- **Multi-Channel**: Works with Shopee, Lazada, TikTok, and other channels

## Technical Implementation

### Database Structure

```sql
-- Main allocation table
marketplace_fee_allocation (
    settlement_id,          -- Link to settlement
    invoice_id,             -- Link to invoice
    allocation_method,      -- 'proportional' or 'exact'
    allocation_base_amount, -- Usually invoice pre-tax amount
    allocation_percentage,  -- % of total settlement
    base_fee_alloc,         -- Allocated marketplace fee
    vat_input_alloc,        -- Allocated VAT on fee
    wht_alloc,              -- Allocated withholding tax
    net_payout_alloc        -- Net amount after deductions
)

-- Reporting view
marketplace_fee_allocation_report (
    -- Combines allocation data with settlement/invoice info
    -- Adds profitability calculations
    -- Provides time dimensions for analysis
)
```

### Key Methods

#### Settlement Model Extensions
- `action_generate_fee_allocations()`: Create allocation records
- `action_view_fee_allocations()`: Open allocation view
- `action_recalculate_fee_allocations()`: Recalculate proportional allocations
- `get_fee_allocation_summary()`: Get allocation summary for validation

#### Fee Allocation Model
- `action_allocate_proportional()`: Calculate proportional allocation
- `action_set_exact_values()`: Set exact allocation values
- `generate_allocations_for_settlement()`: Bulk allocation generation

#### CSV Import Wizard
- `action_import_allocations()`: Process CSV file
- `action_download_template()`: Generate CSV template
- Column mapping and validation features

## Business Benefits

### 1. Detailed Profitability Analysis
- Understand true profitability per invoice after marketplace fees
- Compare performance across different marketplace channels
- Identify high-margin vs low-margin customers

### 2. Accurate Cost Attribution
- Properly allocate marketplace fees to specific sales
- Track VAT and withholding tax impact per transaction
- Support transfer pricing and cost center analysis

### 3. Enhanced Reporting
- Generate detailed commission reports for management
- Support month-end and year-end financial analysis
- Provide data for pricing strategy decisions

### 4. Marketplace Channel Analysis
- Compare fee structures across different marketplaces
- Analyze channel profitability trends over time
- Support channel strategy and negotiation decisions

## Configuration

### 1. Default Allocation Method
Set the preferred allocation method in Settlement records:
- **Proportional**: For settlements without detailed fee breakdown
- **Exact**: For settlements with marketplace-provided fee details

### 2. CSV Import Settings
Configure CSV import parameters:
- File format (delimiter, header row)
- Column mapping for invoice numbers and fee amounts
- Import mode (replace vs update existing allocations)

### 3. Security and Access
Fee allocation functionality is available to users with:
- **Account Invoice** group access
- Read/write access to allocation records
- CSV import/export capabilities

## Sample Workflow

### Typical Monthly Settlement Process

1. **Create Settlement** with customer invoices and deduction amounts
2. **Post Settlement** to generate accounting entries
3. **Generate Fee Allocations** using proportional method
4. **Import CSV Updates** if marketplace provides detailed breakdown
5. **Review Allocations** for accuracy and completeness
6. **Run Analysis Reports** for profitability review
7. **Use Data** for pricing and channel strategy decisions

### CSV Import Example

```csv
Invoice Number,Base Fee,VAT Input,WHT,Customer,Invoice Date,Pre-tax Amount
INV/2024/0001,1250.00,87.50,37.50,Customer A,2024-01-15,25000.00
INV/2024/0002,800.00,56.00,24.00,Customer B,2024-01-16,16000.00
INV/2024/0003,450.00,31.50,13.50,Customer C,2024-01-17,9000.00
```

## Support and Maintenance

### Data Validation
- Automatic validation ensures invoices belong to settlement
- Amount validation prevents negative or excessive allocations
- Method validation ensures consistent allocation approach

### Performance Optimization
- Indexed fields for efficient querying
- Computed fields with storage for fast reporting
- Database view for complex analytical queries

### Troubleshooting
- Import error logging and reporting
- Allocation summary validation
- Mismatch detection between allocated and settlement totals

## Future Enhancements

Potential future improvements:
- **API Integration**: Direct integration with marketplace APIs
- **Advanced Analytics**: Machine learning for fee prediction
- **Multi-Currency**: Support for settlements in different currencies
- **Batch Processing**: Enhanced bulk import/export capabilities
