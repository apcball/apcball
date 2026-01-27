# Marketplace Vendor Bill Features

This enhancement adds vendor bill creation capabilities to the marketplace_settlement module, specifically designed for handling Shopee Tax Invoices (TR) and SPX Receipts (RC).

## Features

### 1. Vendor Bill Creation from Marketplace Documents

The module now supports importing and processing two types of marketplace documents:

#### Shopee Tax Invoices (TR)
- **Document Pattern**: TR followed by alphanumeric characters (e.g., TR2024010001)
- **Default Tax Configuration**:
  - VAT: 7% (Purchase VAT Input Tax)
  - WHT: 3% (Withholding Tax)
- **Common Line Items**:
  - Platform Commission (Account: 6201)
  - Service Fees (Account: 6202)
  - Advertising Fees (Account: 6203)

#### SPX Receipts (RC)
- **Document Pattern**: RC followed by alphanumeric characters (e.g., RC2024010001)
- **Default Tax Configuration**:
  - VAT: 0% (Usually no VAT on logistics)
  - WHT: 1% (Withholding Tax)
- **Common Line Items**:
  - Logistics Fees (Account: 6204)
  - Shipping Charges (Account: 6205)

### 2. Import Methods

#### Manual Entry
- Create individual vendor bill documents through a user-friendly form
- Automatic partner detection based on document type
- Pre-configured tax rates and expense accounts
- Real-time validation of document reference format

#### CSV Import
- Batch import multiple documents from CSV files
- Downloadable CSV template with proper format
- Support for multiple delimiters (comma, semicolon, tab, pipe)
- Error reporting and validation
- Duplicate prevention

### 3. Key Features

#### Duplicate Prevention
- Unique validation on document reference + document type combination
- Prevents accidental re-processing of the same marketplace document
- Clear error messages for duplicate attempts

#### Automatic Account Mapping
- Pre-configured expense accounts for different fee types
- Fallback to default expense accounts if specific codes not found
- Support for custom account codes via CSV import

#### Tax Automation
- Automatic VAT and WHT calculation based on document type
- Support for custom tax rates per line item
- Integration with Odoo's tax system for proper accounting

#### Vendor Bill Integration
- One-click vendor bill creation from marketplace documents
- Proper tax line generation with VAT input and WHT
- Direct navigation to created vendor bills
- State management (Draft → Processed → Cancelled)

## Usage

### Creating Vendor Bills Manually

1. **Navigate**: Accounting → Vendors → Import Documents
2. **Select Document Type**: Choose between "Shopee Tax Invoice (TR)" or "SPX Receipt (RC)"
3. **Choose Import Method**: Select "Manual Entry"
4. **Fill Details**:
   - Document Reference (e.g., TR2024010001)
   - Vendor (auto-selected based on document type)
   - Date
   - Bill Journal
5. **Click Import**: Creates a marketplace vendor bill with default lines
6. **Edit Lines**: Modify amounts, descriptions, and tax rates as needed
7. **Create Vendor Bill**: Click "Create Vendor Bill" to generate the actual accounting entry

### Importing from CSV

1. **Navigate**: Accounting → Vendors → Import Documents
2. **Select Document Type**: Choose document type
3. **Choose Import Method**: Select "CSV Import"
4. **Download Template**: Click "Download Template" for CSV format
5. **Prepare CSV**: Fill the template with your data
6. **Upload File**: Select your CSV file and delimiter
7. **Preview**: Review the data preview
8. **Import**: Click "Import CSV" to process all records

### CSV Format

Required columns:
- `document_reference`: Document number (TR... or RC...)
- `date`: Document date (YYYY-MM-DD or DD/MM/YYYY)
- `partner_name`: Vendor name (optional, uses default if empty)
- `description`: Line description
- `amount`: Line amount (excluding VAT)
- `vat_rate`: VAT percentage (e.g., 7.0 for 7%)
- `wht_rate`: WHT percentage (e.g., 3.0 for 3%)
- `account_code`: Expense account code (optional)

### Managing Vendor Bills

1. **Navigate**: Accounting → Vendors → Vendor Bills
2. **View All Documents**: See all imported marketplace documents
3. **Filter Options**:
   - By document type (Shopee TR / SPX RC)
   - By state (Draft / Processed / Cancelled)
   - By date range
   - By vendor
4. **Actions**:
   - Create vendor bills from draft documents
   - View generated accounting entries
   - Cancel documents if needed
   - Reset cancelled documents to draft

## Configuration

### Default Accounts

The module uses these default account codes:
- 6201: Marketplace Commission
- 6202: Service Fees  
- 6203: Advertising Expense
- 6204: Logistics Expense
- 6205: Shipping Expense

Create these accounts in your chart of accounts or modify the account mapping in the code.

### Default Partners

Create vendor partners for:
- Shopee Thailand (for TR documents)
- SPX Technologies (for RC documents)

The system will auto-detect these partners based on name matching.

### Tax Configuration

Ensure these taxes exist in your system:
- Purchase VAT 7% (for Shopee fees)
- Purchase WHT 3% (for Shopee fees)
- Purchase WHT 1% (for SPX fees)

## Security

Access is controlled by the `account.group_account_invoice` group, ensuring only authorized accounting users can:
- Import marketplace documents
- Create vendor bills
- Modify tax configurations
- Access sensitive financial data

## Technical Notes

### Models Added
- `marketplace.vendor.bill`: Main document model
- `marketplace.vendor.bill.line`: Document line items
- `marketplace.document.import.wizard`: Import wizard

### Sequence
- Vendor bills are auto-numbered with pattern: MVB{YEAR}{00000}

### Validation
- Document reference format validation
- Duplicate prevention across document type + reference
- Required field validation
- Tax rate validation

This enhancement provides a complete solution for managing marketplace vendor bills with proper tax handling, duplicate prevention, and seamless integration with Odoo's accounting system.
