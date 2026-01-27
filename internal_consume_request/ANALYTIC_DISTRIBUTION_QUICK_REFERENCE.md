# Quick Reference: Analytic Distribution in Internal Consume Request

## Files Modified

```
internal_consume_request/
├── __manifest__.py                          [Added 'account' dependency]
├── models/
│   ├── internal_consume_request.py          [Enhanced action_submit() validation]
│   └── internal_consume_request_line.py     [Added analytic fields & constraints]
├── views/
│   └── internal_consume_request_views.xml   [Updated tree view with analytic field]
└── security/
    └── ir.model.access.csv                  [Cleaned up access rules]
```

## Key Code Changes

### 1. Model Fields Added
```python
# internal_consume_request_line.py
analytic_distribution = fields.Json(
    string='Analytic Distribution',
    copy=True,
    store=True,
    default={}
)

analytic_precision = fields.Integer(
    string="Analytic Precision",
    default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic')
)
```

### 2. Validation Constraint
```python
@api.constrains('analytic_distribution')
def _check_analytic_distribution(self):
    for line in self:
        if not line.analytic_distribution or not any(line.analytic_distribution.values()):
            raise ValidationError(
                _('Analytic Distribution is mandatory. Please assign an analytic account to each line.')
            )
```

### 3. Action Validation
```python
# In action_submit() method
for line in self.line_ids:
    if not line.analytic_distribution or not any(line.analytic_distribution.values()):
        raise UserError(
            _('Please enter Analytic Distribution for all items before submitting for approval.')
        )
```

### 4. View Widget
```xml
<field name="analytic_distribution" required="1" widget="analytic_distribution"/>
```

## How It Works

1. **Field Type**: JSON stores key-value pairs of analytic accounts and their percentages
2. **Widget**: `analytic_distribution` provides built-in UI for distribution
3. **Validation**: Two-level validation:
   - Model constraint (prevents invalid saves)
   - Action validation (prevents submission without distribution)
4. **Default**: Empty JSON `{}` that must be populated

## User Workflow

1. Open/Create Consumable Request
2. Add Product Lines
3. In each line, click the Analytic Distribution field
4. Select one or more analytic accounts and set percentages
5. Total should equal 100%
6. Save the line
7. Submit request → Validation checks all lines have distribution

## Error Messages

| Scenario | Message |
|----------|---------|
| Save line without analytic | "Analytic Distribution is mandatory. Please assign an analytic account to each line." |
| Submit request without analytic | "Please enter Analytic Distribution for all items before submitting for approval." |

## Dependencies

- **account** module: For analytic_distribution widget and decimal precision
- **base, hr, stock, mail**: Existing dependencies

## Testing Commands

```bash
# After module upgrade/installation
cd /opt/instance1/odoo17/custom-addons
# Verify module loads without errors
sudo systemctl restart instance1
```

## Database Impact

- New JSON column added to internal_consume_request_line table
- New integer column added for precision
- No migrations needed (Odoo 17 handles automatically)
- Existing records will have empty JSON defaults

---
*Last Updated: December 18, 2025*
