# prompt.md — Budget Dashboard v2 (Analytic Focus + UI Polish)

## 🎯 Objective

Upgrade the existing dashboard to:

* Be **analytic-driven (multi-dimension breakdown)**
* Provide **decision-ready insights**
* Improve **UI/UX to enterprise standard**
* Replace low-value charts with **actionable visualizations**

---

# 🧠 Core Design Principle

> ❌ Old: Aggregate view (BU1 only)
> ✅ New: **Analytic-first + Drill-down + Visual clarity**

---

# 1️⃣ Backend API Upgrade

## A. Extend Main Service

```python
def get_dashboard_data(self, filters):
    return {
        'kpi': self._get_kpi(filters),
        'waterfall': self._get_waterfall(filters),
        'analytic_breakdown': self._get_analytic_breakdown(filters),  # ⭐ NEW
        'stacked_bar': self._get_stacked_bar(filters),                # ⭐ NEW
        'trend': self._get_trend(filters),
        'alerts': self._get_alerts(filters),
    }
```

---

## B. Analytic Breakdown (CORE FEATURE)

```python
def _get_analytic_breakdown(self, filters):
    query = """
        SELECT
            analytic_account_id,
            department_id,
            project_id,
            category,
            SUM(budget_amount) AS budget,
            SUM(fixed_cost) AS fixed,
            SUM(reserved_amount) AS reserved,
            SUM(used_amount) AS used
        FROM monthly_budget_report
        WHERE plan_id = %s
        GROUP BY analytic_account_id, department_id, project_id, category
    """

    self.env.cr.execute(query, [filters['plan_id']])
    rows = self.env.cr.dictfetchall()

    result = []
    for r in rows:
        available = r['budget'] - r['fixed'] - r['reserved'] - r['used']
        utilization = (r['used'] / r['budget']) if r['budget'] else 0

        result.append({
            'analytic': r['analytic_account_id'],
            'department': r['department_id'],
            'project': r['project_id'],
            'category': r['category'],
            'budget': r['budget'],
            'fixed': r['fixed'],
            'reserved': r['reserved'],
            'used': r['used'],
            'available': available,
            'utilization': utilization,
        })

    return result
```

---

## C. Stacked Bar Data

```python
def _get_stacked_bar(self, filters):
    data = self._get_analytic_breakdown(filters)

    return [
        {
            'label': d['analytic'],
            'budget': d['budget'],
            'fixed': d['fixed'],
            'reserved': d['reserved'],
            'used': d['used'],
        }
        for d in data
    ]
```

---

# 2️⃣ OWL Frontend Upgrade

## A. New Component Structure

```javascript
components/
 ├── kpi_cards.js
 ├── analytic_table.js      ⭐ MAIN
 ├── progress_bar.js
 ├── stacked_bar.js
 ├── waterfall_chart.js
 ├── trend_chart.js
 └── alert_panel.js
```

---

# 3️⃣ Analytic Table (Main UI)

## A. Table Layout

```xml
<table class="o_budget_table">
  <thead>
    <tr>
      <th>Analytic</th>
      <th>Department</th>
      <th>Budget</th>
      <th>Fixed</th>
      <th>Reserved</th>
      <th>Used</th>
      <th>Available</th>
      <th>%</th>
    </tr>
  </thead>
  <tbody>
    <t t-foreach="props.data" t-as="row">
      <tr>
        <td><t t-esc="row.analytic"/></td>
        <td><t t-esc="row.department"/></td>
        <td><t t-esc="row.budget"/></td>
        <td><t t-esc="row.fixed"/></td>
        <td><t t-esc="row.reserved"/></td>
        <td><t t-esc="row.used"/></td>
        <td><t t-esc="row.available"/></td>
        <td>
          <ProgressBar value="row.utilization"/>
        </td>
      </tr>
    </t>
  </tbody>
</table>
```

---

## B. Progress Bar Component

```javascript
export class ProgressBar extends Component {
    static props = ['value'];

    get color() {
        if (this.props.value < 0.5) return 'green';
        if (this.props.value < 0.8) return 'yellow';
        return 'red';
    }
}
```

---

# 4️⃣ Stacked Bar Chart

## Replace Heatmap

```javascript
const data = {
    labels: items.map(i => i.label),
    datasets: [
        { label: 'Fixed', data: items.map(i => i.fixed) },
        { label: 'Reserved', data: items.map(i => i.reserved) },
        { label: 'Used', data: items.map(i => i.used) },
    ]
};
```

---

# 5️⃣ Waterfall Chart (UI Polish)

## Color Mapping

```javascript
const colors = {
    total: '#3B82F6',
    fixed: '#8B5CF6',
    reserved: '#F59E0B',
    used: '#EF4444',
    remaining: '#10B981',
};
```

---

# 6️⃣ KPI Enhancement

## Add Burn Rate

```python
burn_rate = used / total if total else 0
```

---

# 7️⃣ Alert Panel

```python
def _get_alerts(self, filters):
    alerts = []

    for line in self._get_analytic_breakdown(filters):
        if line['utilization'] > 0.8:
            alerts.append({
                'type': 'warning',
                'message': f"{line['analytic']} > 80%"
            })

        if line['available'] < 0:
            alerts.append({
                'type': 'error',
                'message': f"{line['analytic']} over budget"
            })

    return alerts
```

---

# 8️⃣ Filters Upgrade

## Add:

```text
Year
Month
Company
Department
Project
Category
```

---

# 9️⃣ UI Styling (IMPORTANT)

## Color Palette

```css
:root {
  --budget: #3B82F6;
  --fixed: #8B5CF6;
  --reserved: #F59E0B;
  --used: #EF4444;
  --available: #10B981;
}
```

---

## Table Styling

```css
.o_budget_table {
  border-radius: 12px;
  overflow: hidden;
}

.o_budget_table tr:hover {
  background: #f9fafb;
}
```

---

# 🔟 Performance Rules

* Use SQL aggregation only (NO Python loops)
* Add indexes:

  * analytic_account_id
  * department_id
  * plan_id
* Response time < 300ms

---

# ✅ Acceptance Criteria

* Dashboard shows per-analytic breakdown
* Users can identify high usage instantly
* UI is clean, readable, and modern
* Charts reflect dimension-based data
* No single aggregated BU-only view

---

# 🚀 Outcome

After upgrade:

❌ Dashboard = static report
✅ Dashboard = **Financial Control Panel**

---

# 📌 Notes

* Analytic breakdown is the PRIMARY view
* Every chart must support decision-making
* Avoid redundant visuals (no useless pie charts)

---
