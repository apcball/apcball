# Concurrency Control - Quick Reference Guide

## Overview

Version 17.0.1.2.1 introduces comprehensive concurrency control to prevent race conditions in FIFO operations. This guide provides quick reference for using the concurrency features.

---

## 🔒 Core Components

### 1. FifoConcurrencyMixin
Abstract model providing concurrency utilities.

**Inheritance:**
```python
class MyModel(models.Model):
    _inherit = ['stock.valuation.layer', 'fifo.concurrency.mixin']
```

### 2. FifoConcurrencyHelper
Helper methods for safe concurrent operations.

**Access:**
```python
helper = self.env['fifo.concurrency.helper']
result = helper.safe_consume_fifo_layers(layers, quantity)
```

---

## 🎯 Decorators

### @with_fifo_lock()
Acquires row-level locks on FIFO queue records.

**Usage:**
```python
@FifoConcurrencyMixin.with_fifo_lock(lock_timeout=10000)
def consume_fifo_layers(self, product, warehouse, quantity):
    # Critical FIFO consumption logic
    # Automatically protected by SELECT FOR UPDATE locks
    pass
```

**Parameters:**
- `lock_timeout`: Timeout in milliseconds (default: 10000)

**Behavior:**
- Uses PostgreSQL SELECT FOR UPDATE NOWAIT
- Fails fast if lock unavailable
- User-friendly error messages in Thai

---

### @with_retry_on_deadlock()
Automatically retries on deadlock with exponential backoff.

**Usage:**
```python
@FifoConcurrencyMixin.with_retry_on_deadlock(max_retries=3, base_delay=0.1)
def update_fifo_layers(self, layers, values):
    # Update logic that might deadlock
    # Automatically retries with increasing delays
    pass
```

**Parameters:**
- `max_retries`: Maximum retry attempts (default: 3)
- `base_delay`: Base delay in seconds, doubles each retry (default: 0.1)

**Retry Schedule:**
- Attempt 1: Immediate
- Attempt 2: Wait 0.1s
- Attempt 3: Wait 0.2s
- Attempt 4: Wait 0.4s

---

### @with_serializable_transaction()
Executes method in SERIALIZABLE isolation level.

**Usage:**
```python
@FifoConcurrencyMixin.with_serializable_transaction()
def critical_fifo_operation(self):
    # Strictest isolation level
    # Prevents all concurrency anomalies
    pass
```

**When to Use:**
- Critical operations requiring absolute consistency
- Financial calculations
- Compliance-sensitive operations

**Trade-off:**
- Higher consistency
- More serialization failures
- Lower throughput

---

## 🔐 Locking Methods

### _lock_fifo_queue()
Locks all valuation layers in FIFO queue for a product at warehouse.

**Usage:**
```python
locked_layers = self._lock_fifo_queue(
    product_id=product,
    warehouse_id=warehouse,
    company_id=self.env.company.id,
    nowait=True
)

# Now safe to consume from locked_layers
for layer in locked_layers:
    # Process layer...
    pass
```

**Parameters:**
- `product_id`: stock.product.product or id
- `warehouse_id`: stock.warehouse or id
- `company_id`: res.company id
- `nowait`: True = fail fast, False = wait for lock

**Returns:**
- Recordset of locked stock.valuation.layer records (ordered FIFO)

**Raises:**
- `UserError`: If lock cannot be acquired (when nowait=True)

---

### _lock_valuation_layer()
Locks specific valuation layer.

**Usage:**
```python
locked_layer = self._lock_valuation_layer(
    layer_id=layer,
    nowait=True
)

# Safe to update locked_layer
locked_layer.write({'remaining_qty': new_value})
```

---

### _validate_no_concurrent_modification()
Checks if layer was modified by another transaction.

**Usage:**
```python
# Read initial value
expected_qty = layer.remaining_qty

# Do some work...

# Before commit, validate no changes
self._validate_no_concurrent_modification(layer, expected_qty)
```

**Raises:**
- `UserError`: If concurrent modification detected

---

## 🛡️ Safe Operations

### safe_consume_fifo_layers()
Atomically consume FIFO layers with proper locking.

**Usage:**
```python
helper = self.env['fifo.concurrency.helper']

result = helper.safe_consume_fifo_layers(
    layers=fifo_queue,
    quantity_to_consume=100.0
)

print(f"Consumed value: {result['consumed_value']}")
print(f"Consumed qty: {result['consumed_qty']}")
print(f"Shortage: {result['shortage_qty']}")
print(f"Updated {len(result['updated_layers'])} layers")
```

**Returns:**
```python
{
    'consumed_value': 5000.0,      # Total cost
    'consumed_qty': 100.0,          # Actual qty consumed
    'updated_layers': [             # List of updates
        {
            'layer_id': 123,
            'qty_consumed': 50.0,
            'value_consumed': 2500.0,
            'unit_cost': 50.0,
            'new_remaining_qty': 0.0,
            'new_remaining_value': 0.0
        },
        # ... more layers
    ],
    'shortage_qty': 0.0             # Unmet demand
}
```

---

### safe_create_valuation_layer()
Creates layer with concurrency check.

**Usage:**
```python
helper = self.env['fifo.concurrency.helper']

layer = helper.safe_create_valuation_layer(
    vals={
        'product_id': product.id,
        'warehouse_id': warehouse.id,
        'quantity': 100.0,
        'value': 5000.0,
    },
    check_concurrency=True
)
```

---

## ⚙️ Configuration Parameters

### Lock Timeout
```xml
<record id="config_fifo_lock_timeout" model="ir.config_parameter">
    <field name="key">stock_fifo_by_location.fifo_lock_timeout</field>
    <field name="value">10000</field>  <!-- milliseconds -->
</record>
```

### Deadlock Retries
```xml
<record id="config_deadlock_max_retries" model="ir.config_parameter">
    <field name="key">stock_fifo_by_location.deadlock_max_retries</field>
    <field name="value">3</field>
</record>

<record id="config_deadlock_base_delay" model="ir.config_parameter">
    <field name="key">stock_fifo_by_location.deadlock_base_delay</field>
    <field name="value">0.1</field>  <!-- seconds -->
</record>
```

### Lock Strategy
```xml
<record id="config_lock_strategy" model="ir.config_parameter">
    <field name="key">stock_fifo_by_location.lock_strategy</field>
    <field name="value">nowait</field>  <!-- or 'wait' -->
</record>
```

### Enable Features
```xml
<record id="config_enable_concurrency_checks" model="ir.config_parameter">
    <field name="key">stock_fifo_by_location.enable_concurrency_checks</field>
    <field name="value">True</field>
</record>

<record id="config_log_concurrency_events" model="ir.config_parameter">
    <field name="key">stock_fifo_by_location.log_concurrency_events</field>
    <field name="value">True</field>
</record>
```

---

## 🎬 Common Scenarios

### Scenario 1: Concurrent Sales of Same Product

**Problem:** Two users selling same product simultaneously might consume same FIFO layers.

**Solution:**
```python
# In _run_fifo() - already implemented
@FifoConcurrencyMixin.with_retry_on_deadlock(max_retries=3)
def _run_fifo(self, quantity, company):
    # Lock FIFO queue
    candidates = self._lock_fifo_queue(
        self.product_id,
        self.warehouse_id,
        company.id,
        nowait=True
    )
    
    # Safe consumption
    helper = self.env['fifo.concurrency.helper']
    result = helper.safe_consume_fifo_layers(candidates, abs(quantity))
    
    # Process result...
```

**Result:** Only one transaction gets the lock, others wait or retry.

---

### Scenario 2: Inter-Warehouse Transfer During Sales

**Problem:** Product being transferred while also being sold.

**Solution:** Both operations lock their respective warehouses independently.

```python
# Source warehouse locks for consumption
source_layers = self._lock_fifo_queue(product, source_wh, company_id)

# Destination warehouse creates new layers (separate transaction)
dest_layer = helper.safe_create_valuation_layer(vals)
```

**Result:** No conflict - different warehouses have separate locks.

---

### Scenario 3: Deadlock Prevention

**Problem:** Transaction A locks Layer 1 then Layer 2, Transaction B locks Layer 2 then Layer 1.

**Solution:** Always lock in same order (by create_date, then id).

```python
# In safe_consume_fifo_layers() - already implemented
locked_layers = self.env.cr.execute("""
    SELECT id FROM stock_valuation_layer
    WHERE id IN %s
    ORDER BY create_date ASC, id ASC  -- Consistent order!
    FOR UPDATE
""", (layer_ids,))
```

**Result:** Deadlocks become serialization failures, automatically retried.

---

## 📊 Monitoring & Debugging

### Check Active Locks
```sql
SELECT 
    l.pid,
    l.mode,
    l.granted,
    svl.id as layer_id,
    svl.product_id,
    svl.warehouse_id,
    svl.remaining_qty
FROM pg_locks l
JOIN stock_valuation_layer svl ON svl.id = l.objid
WHERE l.locktype = 'tuple'
  AND svl.remaining_qty > 0
ORDER BY l.granted DESC, svl.create_date;
```

### Check Deadlocks
```sql
SELECT * FROM pg_stat_database WHERE datname = current_database();
-- Look at deadlocks column
```

### View Lock Waits
```sql
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_statement,
    blocking_activity.query AS blocking_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks 
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

---

## ⚠️ Best Practices

### DO ✅
1. **Use decorators** for critical operations
2. **Lock in consistent order** (by create_date, id)
3. **Keep transactions short** - lock, update, commit
4. **Handle UserError** for lock timeouts
5. **Log concurrency events** for monitoring
6. **Use safe_consume_fifo_layers()** instead of manual loops

### DON'T ❌
1. **Don't hold locks** for long periods
2. **Don't lock unnecessarily** - only critical sections
3. **Don't use serializable** for everything (overkill)
4. **Don't ignore lock timeout errors** - inform users
5. **Don't lock in random order** - causes deadlocks

---

## 🚀 Performance Tips

1. **Batch Operations**: Lock once, process multiple layers
2. **Short Transactions**: Acquire lock → update → commit → release
3. **Index Usage**: Composite indexes on (product_id, warehouse_id, remaining_qty)
4. **Limit Queue Size**: Use limit parameter in _get_fifo_queue()
5. **Monitor Deadlocks**: Check pg_stat_database regularly

---

## 🆘 Troubleshooting

### Error: "ระบบกำลังประมวลผล FIFO อยู่"
**Cause:** Lock timeout - another transaction holds the lock.

**Solutions:**
1. Wait a moment and retry
2. Check for long-running transactions
3. Increase lock_timeout if needed

### Error: "ระบบไม่สามารถประมวลผล FIFO ได้"
**Cause:** Max retries exceeded after deadlocks.

**Solutions:**
1. Check for application-level deadlocks
2. Increase max_retries
3. Review lock ordering in custom code

### Error: "ตรวจพบการแก้ไขพร้อมกัน!"
**Cause:** Concurrent modification detected.

**Solutions:**
1. Retry the operation
2. Check for missing locks in custom code
3. Enable detect_concurrent_modifications logging

---

## 📚 References

- **PostgreSQL Row-Level Locking**: https://www.postgresql.org/docs/current/explicit-locking.html
- **Transaction Isolation**: https://www.postgresql.org/docs/current/transaction-iso.html
- **Deadlock Detection**: https://www.postgresql.org/docs/current/runtime-config-locks.html

---

## 📝 Summary

**Key Points:**
- ✅ Use `@with_fifo_lock()` for critical operations
- ✅ Use `@with_retry_on_deadlock()` for atomic updates
- ✅ Use `safe_consume_fifo_layers()` for FIFO consumption
- ✅ Always lock in consistent order (create_date, id)
- ✅ Keep transactions short
- ✅ Monitor concurrency events

**Benefits:**
- 🛡️ Data consistency guaranteed
- 🔄 Automatic deadlock recovery
- 🚀 High-concurrency support
- 📊 Production-ready reliability
