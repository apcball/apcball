# Dashboard Caching Implementation

## Overview

This document describes the dashboard caching implementation for the Warranty Management module. The caching system provides instant dashboard loading while keeping data up-to-date through intelligent updates.

## Architecture

### Components

1. **Cache Model** (`warranty.dashboard.cache`)
   - Stores pre-calculated dashboard metrics
   - Tracks cache status and performance
   - Handles scheduled and triggered updates

2. **Dashboard Model** (`warranty.dashboard`)
   - Uses cached data instead of real-time calculations
   - Provides fallback to real-time data if cache is unavailable
   - Includes manual refresh options

3. **Scheduled Job** (`ir.cron`)
   - Updates cache every 15 minutes
   - Runs during business hours
   - Includes error handling and retry mechanisms

4. **Data Triggers**
   - Automatically updates cache when warranties or claims change
   - Implements debouncing to prevent excessive updates
   - Batches multiple changes for efficiency

5. **Visual Indicators**
   - Shows cache status (Live, Stale, Error, Updating)
   - Displays last update time and countdown timer
   - Provides manual refresh buttons

## Features

### Performance Benefits

- **Instant Loading**: Dashboard loads in <0.5 seconds regardless of data volume
- **Smart Updates**: Only updates when data changes or at scheduled intervals
- **Background Processing**: Updates don't block user interface
- **Scalability**: Handles thousands of records efficiently

### User Experience

- **Real-time Feel**: Data appears current with auto-refresh
- **Transparency**: Clear indicators of data freshness
- **Control**: Manual refresh options for immediate updates
- **Reliability**: Fallback mechanisms ensure dashboard always works

## Configuration

### Cache Settings

Navigate to **Settings > Warranty Management** to configure:

- **Enable Automatic Cache Updates**: Turn automatic updates on/off
- **Debounce Delay**: Minimum time between automatic updates (default: 2 minutes)
- **Batch Update Threshold**: Number of changes before triggering batch update (default: 5)

### Cron Job

The cache update job is configured in **Technical > Automation > Scheduled Actions**:

- **Name**: Update Warranty Dashboard Cache
- **Model**: Warranty Dashboard Cache
- **Interval**: Every 15 minutes
- **Priority**: 5 (high priority)

## Implementation Details

### Cache Model Fields

```python
# Core metrics
total_warranties = fields.Integer()
active_warranties = fields.Integer()
expired_warranties = fields.Integer()
near_expiry_warranties = fields.Integer()
claimed_warranties = fields.Integer()

# Percentages
active_percentage = fields.Float()
expired_percentage = fields.Float()
claimed_percentage = fields.Float()

# Additional metrics
claims_this_month = fields.Integer()
claims_last_month = fields.Integer()

# Tracking
last_update = fields.Datetime()
cache_status = fields.Selection([
    ('valid', 'Valid'),
    ('expired', 'Expired'),
    ('updating', 'Updating'),
    ('error', 'Error'),
])
```

### Update Mechanism

```python
def _update_all_metrics(self):
    """Update all cached metrics efficiently"""
    # Uses SQL queries for performance
    self._cr.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN state = 'active' THEN 1 END) as active,
            COUNT(CASE WHEN state = 'expired' OR end_date < CURRENT_DATE THEN 1 END) as expired,
            COUNT(CASE WHEN state = 'active' AND end_date >= CURRENT_DATE 
                     AND end_date <= CURRENT_DATE + INTERVAL '30 days' THEN 1 END) as near_expiry,
            COUNT(CASE WHEN EXISTS(SELECT 1 FROM warranty_claim wc WHERE wc.warranty_card_id = warranty_card.id) 
                     THEN 1 END) as claimed
        FROM warranty_card
    """)
    
    # Updates cache with atomic write
    self.write({
        'total_warranties': result['total'],
        'active_warranties': result['active'],
        # ... other metrics
    })
```

### Trigger System

```python
def _trigger_update(self, trigger_type, records=None):
    """Handle cache update triggers"""
    # High priority triggers update immediately
    if trigger_type in ['warranty_card_created', 'warranty_claim_created']:
        self._update_all_metrics_async()
    else:
        # Debounce other triggers
        self._schedule_debounced_update()
```

## Testing

### Performance Tests

Run performance benchmarks:

```bash
python -m odoo -d your_db --test-enable --test-tags=PerformanceBenchmark
```

### Unit Tests

Test cache functionality:

```bash
python -m odoo -d your_db --test-enable --test-tags=TestDashboardCache
```

## Troubleshooting

### Common Issues

1. **Cache Not Updating**
   - Check if cron job is active
   - Verify trigger settings
   - Review error logs

2. **Slow Updates**
   - Check database performance
   - Review query optimization
   - Consider increasing debounce delay

3. **Memory Issues**
   - Monitor cache size
   - Adjust batch thresholds
   - Review server resources

### Debug Mode

Enable debug logging:

```python
# In odoo.conf
log_level = debug
log_handler = buz_warranty_management:DEBUG
```

### Manual Cache Reset

```python
# In Odoo shell
env['warranty.dashboard.cache'].search([]).unlink()
env['warranty.dashboard.cache'].create({})._update_all_metrics()
```

## Best Practices

1. **Monitor Performance**: Regularly check update times and error rates
2. **Adjust Settings**: Tune debounce and batch settings based on usage patterns
3. **Plan Capacity**: Ensure server resources can handle peak loads
4. **Test Changes**: Always test configuration changes in development environment
5. **Document Changes**: Keep track of custom modifications for future reference

## Future Enhancements

Potential improvements to consider:

1. **Multi-level Caching**: Implement L1/L2 cache hierarchy
2. **Predictive Updates**: ML-based prediction of optimal update times
3. **Distributed Caching**: Redis/Memcached for multi-server deployments
4. **Real-time Subscriptions**: WebSocket-based real-time updates
5. **Advanced Analytics**: More sophisticated metrics and trend analysis