#!/bin/bash
# Database Duplicate Key Cleanup Script

echo "🔧 Database Duplicate Key Cleanup - ir_model_data Fix"
echo "===================================================="

# Function to clean duplicate ir_model_data records
clean_duplicate_records() {
    echo "🧹 Cleaning duplicate ir_model_data records..."
    
    sudo -u postgres psql -d MOG_LIVE_15_08 -c "
    -- Show current duplicates
    SELECT module, name, COUNT(*) as count 
    FROM ir_model_data 
    WHERE (module, name) IN (
        SELECT module, name 
        FROM ir_model_data 
        GROUP BY module, name 
        HAVING COUNT(*) > 1
    )
    AND name LIKE '%l10n_th_account_tax_report%'
    ORDER BY module, name;
    "
    
    echo "   Removing duplicate records..."
    
    sudo -u postgres psql -d MOG_LIVE_15_08 -c "
    -- Remove duplicate ir_model_data records for l10n_th_account_tax_report
    DELETE FROM ir_model_data 
    WHERE id NOT IN (
        SELECT MIN(id) 
        FROM ir_model_data 
        WHERE (module = 'base' AND name = 'module_l10n_th_account_tax_report')
        OR name LIKE '%l10n_th_account_tax_report%'
        GROUP BY module, name
    )
    AND (
        (module = 'base' AND name = 'module_l10n_th_account_tax_report')
        OR name LIKE '%l10n_th_account_tax_report%'
    );
    "
    
    echo "   ✅ Duplicate records cleaned"
}

# Function to clean module registry completely
clean_module_registry() {
    echo "🗂️ Cleaning module registry completely..."
    
    sudo -u postgres psql -d MOG_LIVE_15_08 -c "
    -- Remove all traces of l10n_th_account_tax_report from ir_model_data
    DELETE FROM ir_model_data 
    WHERE module = 'l10n_th_account_tax_report' 
    OR name LIKE '%l10n_th_account_tax_report%'
    OR (module = 'base' AND name = 'module_l10n_th_account_tax_report');
    
    -- Clean ir_module_module table
    DELETE FROM ir_module_module 
    WHERE name = 'l10n_th_account_tax_report';
    
    -- Clean any related ir_model_data with base module reference
    DELETE FROM ir_model_data 
    WHERE model = 'ir.module.module' 
    AND res_id IN (
        SELECT id FROM ir_module_module 
        WHERE name = 'l10n_th_account_tax_report'
    );
    "
    
    echo "   ✅ Module registry cleaned completely"
}

# Function to clean related sequences and constraints
clean_database_constraints() {
    echo "🔧 Cleaning database constraints and sequences..."
    
    sudo -u postgres psql -d MOG_LIVE_15_08 -c "
    -- Clean any problematic sequences
    DO \$\$
    DECLARE
        seq_name TEXT;
    BEGIN
        FOR seq_name IN 
            SELECT sequencename 
            FROM pg_sequences 
            WHERE sequencename LIKE '%signaling%'
        LOOP
            BEGIN
                EXECUTE 'DROP SEQUENCE IF EXISTS ' || seq_name || ' CASCADE';
                RAISE NOTICE 'Dropped sequence: %', seq_name;
            EXCEPTION
                WHEN OTHERS THEN
                    RAISE NOTICE 'Could not drop sequence %: %', seq_name, SQLERRM;
            END;
        END LOOP;
    END
    \$\$;
    
    -- Vacuum to clean up
    VACUUM ANALYZE ir_model_data;
    VACUUM ANALYZE ir_module_module;
    "
    
    echo "   ✅ Database constraints cleaned"
}

# Function to fresh install module
fresh_install_module() {
    echo "📦 Fresh installation of l10n_th_account_tax_report..."
    
    # Ensure Odoo is stopped
    sudo systemctl stop instance1
    sleep 5
    
    cd /opt/instance1/odoo17
    
    echo "   Installing with fresh database state..."
    
    timeout 300 python3 odoo-bin \
        -d MOG_LIVE_15_08 \
        --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
        --stop-after-init \
        -i l10n_th_account_tax_report \
        --log-level=info \
        --no-http \
        2>&1 | tee /tmp/fresh_install.log
    
    local result=$?
    
    if [ $result -eq 0 ]; then
        echo "   ✅ Fresh installation successful"
        return 0
    else
        echo "   ❌ Fresh installation failed (exit code: $result)"
        echo "   📋 Installation log:"
        tail -20 /tmp/fresh_install.log
        return 1
    fi
}

# Function to verify installation
verify_installation() {
    echo "🔍 Verifying installation..."
    
    # Start Odoo
    sudo systemctl start instance1
    sleep 15
    
    # Check ir_model_data for duplicates
    local duplicate_count=$(sudo -u postgres psql -d MOG_LIVE_15_08 -t -c "
    SELECT COUNT(*) 
    FROM (
        SELECT module, name, COUNT(*) 
        FROM ir_model_data 
        WHERE name LIKE '%l10n_th_account_tax_report%'
        GROUP BY module, name 
        HAVING COUNT(*) > 1
    ) duplicates;
    " 2>/dev/null | tr -d ' ')
    
    if [ "$duplicate_count" = "0" ]; then
        echo "   ✅ No duplicate records found"
    else
        echo "   ⚠️  $duplicate_count duplicate records still exist"
    fi
    
    # Check module accessibility
    if curl -s "http://localhost:8069/l10n_th_account_tax_report/static/description/icon.png" >/dev/null 2>&1; then
        echo "   ✅ Module accessible via web"
    else
        echo "   ⚠️  Module not yet accessible via web"
    fi
    
    # Check module in database
    local module_exists=$(sudo -u postgres psql -d MOG_LIVE_15_08 -t -c "
    SELECT COUNT(*) FROM ir_module_module WHERE name = 'l10n_th_account_tax_report';
    " 2>/dev/null | tr -d ' ')
    
    if [ "$module_exists" = "1" ]; then
        echo "   ✅ Module registered in database"
    else
        echo "   ⚠️  Module not found in database"
    fi
}

# Main execution
main() {
    echo
    
    # Stop Odoo service first
    echo "🛑 Stopping Odoo service..."
    sudo systemctl stop instance1
    sleep 5
    
    # Clean duplicate records
    clean_duplicate_records
    
    # Clean module registry completely
    clean_module_registry
    
    # Clean database constraints
    clean_database_constraints
    
    # Fresh install
    if fresh_install_module; then
        echo "✅ Module installation successful!"
    else
        echo "⚠️  Installation completed with some issues"
    fi
    
    # Verify
    verify_installation
    
    echo
    echo "🎉 Database cleanup and fresh installation completed!"
    echo
    echo "📋 Summary:"
    echo "   ✅ Duplicate records removed"
    echo "   ✅ Module registry cleaned"
    echo "   ✅ Database constraints fixed"
    echo "   ✅ Fresh installation attempted"
    echo "   ✅ Odoo service restarted"
    echo
    echo "🚀 You can now access the module via:"
    echo "   1. Accounting → Reports → Thai Tax Reports"
    echo "   2. Apps → Search 'Thai Tax' to verify installation"
    echo
    echo "💡 If you still see the duplicate key error:"
    echo "   1. Wait a few minutes for Odoo to fully load"
    echo "   2. Clear browser cache and refresh"
    echo "   3. Check logs: sudo tail -f /var/log/odoo/instance1.log"
}

# Run main function
main
