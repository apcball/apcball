---
name: frontend-dev
description: Structured frontend development workflow — design user flows, component trees, state management, API contracts, UI states, and Odoo 17 OWL/QWeb frontend before writing code. Use when creating UI screens, components, layouts, connecting APIs, managing state, forms, validation, or building Odoo 17 frontend (OWL components, QWeb templates, assets).
whenToUse: When user asks to build or modify a frontend UI/screen/dashboard, create components, handle layouts/responsive design, connect APIs, manage state/forms/validation, build Odoo 17 OWL components or QWeb templates, or review frontend code before commit/PR.
---

# Frontend Dev Skill

Core principle: **Frontend ที่ดีต้องเริ่มจาก user flow ไม่ใช่เริ่มจาก code**

Follow this thinking order:

```text
User Goal → User Flow → Screen Structure → Component Tree → State & Data Flow → API Contract → UI States → Implementation → Test & Review
```

If you cannot answer: "User ทำอะไร → หน้าจอแสดงอะไร → state อยู่ไหน → data มาจากไหน → error เป็นยังไง" — **do not start writing frontend code yet.** Ask clarification questions first.

## STEP 1: Understand User Goal

Before writing any code, answer:

- ผู้ใช้คือใคร?
- ผู้ใช้ต้องการทำอะไร?
- งานนี้เกิดขึ้นใน context ไหน?
- Success คืออะไร?
- Failure case มีอะไร?

Output format:

```md
## User Goal
- User: ...
- Goal: ...
- Context: ...
- Success Criteria:
  - ...
- Failure Cases:
  - ...
```

## STEP 2: Map User Flow

Write the flow before designing UI. Include every branch:

```text
Open page → Load data → User fills form → Validate input → Submit → Show success / error
```

Required branches:

- Loading
- Empty state
- Error state
- Permission denied
- Validation failed
- Success state

## STEP 3: Design Screen Structure

Break the page into sections:

```text
Page
├── Header / Toolbar
├── Filter / Search
├── Content Area
│   ├── List / Table / Card
│   └── Empty State
├── Form / Modal / Wizard
└── Footer / Actions
```

Checklist:

- [ ] Primary action is clear
- [ ] Secondary actions only where necessary
- [ ] Not cramming all logic into one page
- [ ] Mobile/responsive considered from the start
- [ ] Empty/error/loading states covered

## STEP 4: Component Design

Design the component tree before implementing:

```text
FeaturePage
├── FeatureToolbar
├── FeatureFilters
├── FeatureTable
│   └── FeatureRow
└── FeatureFormModal
```

Component rules:

- One responsibility per component
- Separate presentational from container/data components
- Avoid prop drilling deeper than 2-3 levels
- Names must convey business meaning, not just visual

Naming examples:

```
✅ PurchaseApprovalTable, StockCardFilterPanel, CustomerCreditWarning
❌ Table1, MyComponent, DataBox
```

## STEP 5: State & Data Flow

Categorize state into 4 groups:

| Type | Example | Where to store |
|------|---------|---------------|
| Server State | records, user, permissions | query/store/service |
| UI State | modal open, selected tab | local component |
| Form State | input values, validation | form handler |
| Derived State | totals, filtered list | compute from source |

Rules:

- Do not duplicate server data in local state unnecessarily
- Derived state: compute, don't manually sync
- Loading/error must be tied to data source
- Mutations must have success/error handling

## STEP 6: API / Backend Contract

Define the contract before connecting:

```md
## API Contract
Endpoint/Method: ...
Input:
- field: type, required?, rule
Output:
- field: type
Errors:
- 400 validation
- 403 permission
- 404 not found
- 500 server error
```

Checklist:

- [ ] Request/response clearly defined
- [ ] Permission rules clear
- [ ] Validation on both frontend and backend
- [ ] Error messages user-friendly
- [ ] Retry/refresh strategy if needed

## STEP 7: UI States

Every page must handle these states where applicable:

- Default
- Loading (skeleton/spinner)
- Empty (message + create button)
- Error (retry button)
- Permission denied
- Dirty form / unsaved changes
- Submitting (disable submit)
- Success (toast + refresh)

## STEP 8: Implementation Rules

### General

- Semantic HTML where possible
- Avoid inline styles when project has a design system
- No magic numbers
- Extract constants/helpers for repeated logic
- Form validation must be readable
- Error handling must never be silent

### JavaScript / TypeScript

- Clear names
- One function = one responsibility
- Avoid deeply nested conditions
- Separate pure logic from UI components
- Use optional chaining consciously, don't hide bugs

### CSS

- Use responsive units
- Consistent spacing scale
- No `!important` unless necessary
- Consider dark/light mode if project supports it
- Handle overflow and long text

## Odoo 17 Frontend

When working inside Odoo 17 modules.

### Assets

Declare in `__manifest__.py`:

```python
'assets': {
    'web.assets_backend': [
        'module_name/static/src/**/*.js',
        'module_name/static/src/**/*.xml',
        'module_name/static/src/**/*.scss',
    ],
}
```

### OWL Component Pattern

Recommended structure:

```text
module_name/static/src/components/my_component/
├── my_component.js
├── my_component.xml
└── my_component.scss
```

Rules:

- JS class: PascalCase
- Template `t-name`: `module_name.ComponentName`
- Extract service/API calls from component if complex
- Use `useState`, `onWillStart`, Odoo services per pattern

### QWeb / XML

- Template must have clear `t-name`
- Avoid heavy logic in template
- Use `t-if`, `t-foreach` readably
- Escape/display data safely

### Odoo 17 View Reminder

**No `attrs=` in Odoo 17.** Use direct attributes:

```xml
<!-- ✅ Odoo 17 -->
<field name="amount" invisible="state != 'draft'" readonly="state == 'done'"/>

<!-- ❌ Old syntax -->
<field name="amount" attrs="{'invisible': [('state', '!=', 'draft')]}"/>
```

### Odoo UX Rules

- Respect existing Odoo design patterns
- Use action/menu/view per convention
- Don't build custom UI when standard view works
- Security always on backend — frontend is UX guard only

## Accessibility Checklist

- [ ] Use `<button>` for actions, not clickable `<div>`
- [ ] Inputs have labels
- [ ] Modal: focus trap + closeable
- [ ] Keyboard navigation works
- [ ] Color contrast readable
- [ ] Icon-only buttons have `aria-label`/title
- [ ] Error messages linked to fields

## Performance Checklist

- [ ] No unnecessary duplicate fetches
- [ ] Paginate / lazy load for large data
- [ ] Debounce search/filter
- [ ] Memoize only where needed
- [ ] Optimize images
- [ ] Avoid rendering entire large lists at once
- [ ] Bundle/assets not oversized

## Code Review Checklist

Before PR:

- [ ] User flow matches requirement
- [ ] Components well-separated
- [ ] No duplicate state
- [ ] API errors handled
- [ ] Loading/empty/error states complete
- [ ] Accessibility basics pass
- [ ] Responsive not broken
- [ ] No console.log / debug code
- [ ] No hardcoded text that should be translated
- [ ] No secrets/API keys in frontend

## Definition of Done

- [ ] User flow works per requirement
- [ ] Loading / Empty / Error states complete
- [ ] Form validation correct and readable
- [ ] API success/error handled
- [ ] Permission cases don't break
- [ ] Responsive layout passes key breakpoints
- [ ] Accessibility basics pass
- [ ] No console.log / debug code
- [ ] No secrets/API keys in frontend
- [ ] Code review checklist passed

## Common Pitfalls

1. Start writing components before understanding user flow
2. Skip empty/error/loading states
3. Duplicate state in multiple places until sync breaks
4. Put critical business rules in frontend only
5. Make components too large
6. Forget permission/record rules
7. Hardcode labels/text that should be translated
8. Ignore mobile/responsive
9. Use old Odoo XML syntax in Odoo 17 (`attrs=`)
10. Debug code slips into PR

## Output Format

When using this skill, structure your output as:

```md
## Frontend Plan

### 1. User Goal
...

### 2. User Flow
...

### 3. Screen Structure
...

### 4. Component Tree
...

### 5. State & Data Flow
...

### 6. API Contract
...

### 7. UI States
...

### 8. Implementation Tasks
- [ ] ...

### 9. Test Plan
...

### 10. Risks / Open Questions
...
```
