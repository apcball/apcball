-- SQL script to verify BOQ Material Requisition Wizard access rights
-- Run this in your Odoo database to check if access rights are properly loaded

-- Check if the wizard models exist
SELECT 
    model,
    name
FROM ir_model 
WHERE model IN ('boq.material.requisition.wizard', 'boq.material.requisition.wizard.line')
ORDER BY model;

-- Check access rights for the wizard models
SELECT 
    ima.name as access_name,
    im.model,
    rg.name as group_name,
    ima.perm_read,
    ima.perm_write,
    ima.perm_create,
    ima.perm_unlink
FROM ir_model_access ima
JOIN ir_model im ON ima.model_id = im.id
LEFT JOIN res_groups rg ON ima.group_id = rg.id
WHERE im.model IN ('boq.material.requisition.wizard', 'boq.material.requisition.wizard.line')
ORDER BY im.model, rg.name;

-- Check if the wizard action exists
SELECT 
    name,
    res_model,
    view_mode,
    target,
    context
FROM ir_actions_act_window 
WHERE res_model = 'boq.material.requisition.wizard';

-- Check security groups
SELECT 
    name,
    category_id
FROM res_groups 
WHERE name LIKE '%Job Costing%' OR name LIKE '%Material Requisition%'
ORDER BY name;

-- Check if current user has access to required groups
-- (Replace 'your_username' with actual username)
SELECT 
    u.login,
    rg.name as group_name
FROM res_users u
JOIN res_groups_users_rel rgur ON u.id = rgur.uid
JOIN res_groups rg ON rgur.gid = rg.id
WHERE u.login = 'admin' -- Change this to your username
  AND (rg.name LIKE '%Job Costing%' OR rg.name LIKE '%Material Requisition%')
ORDER BY rg.name;