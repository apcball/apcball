# Cron Job Security Fix

## Issue Fixed
The module installation was failing with the error:
```
forbidden opcode(s) in "...": IMPORT_NAME, IMPORT_FROM
```

## Root Cause
Odoo's security system prevents the use of import statements in cron job code fields for security reasons. The original cron job was trying to import `datetime` and `timedelta` directly in the XML code field.

## Solution Applied

### 1. Created Model Method
Added a `cleanup_old_logs()` method to the `backdate.log` model that:
- Safely imports required modules within the method
- Gets retention period from system parameters
- Performs the cleanup operation
- Logs the results

### 2. Updated Cron Job
Changed the cron job code from:
```python
# Clean backdate logs older than 1 year
from datetime import datetime, timedelta
cutoff_date = datetime.now() - timedelta(days=365)
old_logs = model.search([('create_date', '<', cutoff_date)])
old_logs.unlink()
```

To:
```python
model.cleanup_old_logs()
```

### 3. Added Configuration
- Added `backdate_log_retention_days` setting (default: 365 days)
- Added the setting to the configuration page
- Made retention period configurable (0 = keep forever)

### 4. Enhanced Logging
- Added proper logging to track cleanup operations
- Added import for logging module in backdate_log.py

## Benefits
- ✅ Secure: No import statements in XML
- ✅ Configurable: Retention period can be adjusted
- ✅ Auditable: Cleanup operations are logged
- ✅ Safe: Method includes proper error handling
- ✅ Flexible: Can be disabled by setting retention to 0

## Configuration
After installation, administrators can:
1. Go to Settings > General Settings > Backdate
2. Set "Log Retention Days" (default: 365)
3. Enable the cron job if automatic cleanup is desired
4. The cron job runs monthly by default but is initially disabled