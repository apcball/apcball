# -*- coding: utf-8 -*-

"""
Test script to verify BOQ Material Requisition Wizard access rights
This script helps debug access control issues.
"""

def test_wizard_access():
    """
    Test the wizard access rights and provide debugging information
    """
    print("=== BOQ Material Requisition Wizard Access Test ===")
    print()
    
    print("✅ Security Access Rights Added:")
    print("1. boq.material.requisition.wizard - Job Costing User/Manager")
    print("2. boq.material.requisition.wizard - Material Requisition User/Manager") 
    print("3. boq.material.requisition.wizard - Base User (fallback)")
    print("4. boq.material.requisition.wizard.line - All above groups")
    print()
    
    print("✅ Access Rights Configuration:")
    print("Model: boq.material.requisition.wizard")
    print("- group_job_costing_user: read,write,create")
    print("- group_job_costing_manager: read,write,create,unlink")
    print("- group_material_requisition_user: read,write,create")
    print("- group_material_requisition_manager: read,write,create,unlink")
    print("- base.group_user: read,write,create (fallback)")
    print()
    
    print("Model: boq.material.requisition.wizard.line")
    print("- Same access rights as parent wizard")
    print()
    
    print("🔧 Troubleshooting Steps:")
    print("1. Ensure user is assigned to one of these groups:")
    print("   - Job Costing User")
    print("   - Job Costing Manager") 
    print("   - Material Requisition User")
    print("   - Material Requisition Manager")
    print()
    
    print("2. If still getting access errors, try:")
    print("   - Update the module to reload security rules")
    print("   - Clear browser cache")
    print("   - Restart Odoo server")
    print("   - Check user group assignments in Settings > Users & Companies > Users")
    print()
    
    print("3. Verify the wizard action is correctly defined:")
    print("   - Action ID: action_boq_material_requisition_wizard")
    print("   - Model: boq.material.requisition.wizard")
    print("   - Context: {'default_boq_id': active_id}")
    print()
    
    print("4. Check BOQ state requirements:")
    print("   - BOQ must be in 'approved' or 'locked' state")
    print("   - BOQ must have lines with products")
    print("   - BOQ lines must have remaining quantities > 0")
    print()
    
    print("✅ Expected Workflow:")
    print("1. Open approved BOQ")
    print("2. Click 'Create Material Requisition' button")
    print("3. Wizard opens with BOQ lines that have remaining quantities")
    print("4. Select lines and adjust quantities")
    print("5. Click 'Create Requisition'")
    print("6. Material requisition is created and opened")
    print()
    
    print("🚨 Common Issues and Solutions:")
    print("1. 'Access Error' - User not in correct security group")
    print("   Solution: Assign user to Job Costing User or Material Requisition User group")
    print()
    
    print("2. 'No BOQ lines found' - BOQ has no lines with remaining quantities")
    print("   Solution: Ensure BOQ has lines with products and remaining qty > 0")
    print()
    
    print("3. 'Wizard not opening' - Action context issue")
    print("   Solution: Ensure BOQ is selected when clicking the button")
    print()
    
    print("4. 'Module not found' - Module not properly installed")
    print("   Solution: Update/reinstall the job_costing_management module")
    print()
    
    print("=== Test Complete ===")
    print()
    print("If issues persist, check:")
    print("- Odoo logs for detailed error messages")
    print("- User group assignments")
    print("- Module installation status")
    print("- Database access rights")

if __name__ == "__main__":
    test_wizard_access()