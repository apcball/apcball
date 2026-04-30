import sys

def migrate(env):
    print("Starting Budget Migration...")
    WeeklyPlan = env['weekly.budget.plan']
    MonthlyPlan = env['monthly.budget.plan']
    
    weekly_plans = WeeklyPlan.search([('monthly_plan_id', '=', False)])
    if not weekly_plans:
        print("No weekly plans to migrate.")
        return

    # Group by month, year, company
    groups = {}
    for wp in weekly_plans:
        key = (wp.month, wp.year, wp.company_id.id)
        if key not in groups:
            groups[key] = []
        groups[key].append(wp)
        
    for key, w_plans in groups.items():
        month, year, company_id = key
        # Create monthly plan
        m_plan = MonthlyPlan.create({
            'month': month,
            'year': str(year),
            'company_id': company_id,
            'total_budget': sum(wp.total_monthly_budget for wp in w_plans)
        })
        print(f"Created Monthly Plan {m_plan.name} for {month}/{year}")
        
        # Link weekly plans
        for wp in w_plans:
            wp.monthly_plan_id = m_plan.id
            
            # Create a simple 100% allocation if we can guess the department, or leave blank
            dept_id = wp.department_id.id if wp.department_id else False
            if not dept_id and wp.line_ids:
                # find first dept
                for line in wp.line_ids:
                    if line.department_id:
                        dept_id = line.department_id.id
                        wp.department_id = dept_id
                        break
            
            if dept_id:
                # check if allocation exists for this dept
                alloc = env['monthly.budget.allocation'].search([
                    ('plan_id', '=', m_plan.id),
                    ('department_id', '=', dept_id)
                ], limit=1)
                if not alloc:
                    env['monthly.budget.allocation'].create({
                        'plan_id': m_plan.id,
                        'department_id': dept_id,
                        'percentage': 0.0 # Will need manual adjustment
                    })
        m_plan.action_confirm()

    print("Migration Complete.")

# When run via Odoo Shell:
# env.cr.commit()
