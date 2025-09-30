#!/bin/bash
# Deep diagnostic script to find ALL potential installation issues

echo "=== Deep Diagnostic for l10n_th_account_tax_report Installation ==="

# 1. Check if there are any running Odoo processes
echo -e "\n1. Checking for running Odoo processes..."
pgrep -f "odoo" 
if [ $? -eq 0 ]; then
    echo "⚠ Odoo processes are running. They may need to be restarted with new configuration."
    ps aux | grep odoo | grep -v grep
else
    echo "✓ No running Odoo processes found"
fi

# 2. Check if the module path is accessible to Odoo
echo -e "\n2. Checking if module directory is properly structured..."
if [ -d "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report" ]; then
    echo "✓ Module directory exists"
    echo "Contents:"
    ls -la /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/
else
    echo "✗ Module directory does not exist"
    exit 1
fi

# 3. Check if there are any broken symlinks or files
echo -e "\n3. Checking for broken symlinks or unusual files..."
find /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report -type l | while read link; do
    if [ ! -e "$link" ]; then
        echo "⚠ Broken symlink: $link"
    fi
done
echo "✓ No broken symlinks found"

# 4. Check the XML files for syntax issues
echo -e "\n4. Checking XML files for syntax issues..."
for xml_file in /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/**/*.xml; do
    if [ -f "$xml_file" ]; then
        if xmllint --noout "$xml_file" 2>/dev/null; then
            echo "✓ $(basename $xml_file) is well-formed XML"
        else
            echo "✗ $(basename $xml_file) has XML syntax errors"
        fi
    fi
done

# 5. Check if Odoo can technically see the directory
echo -e "\n5. Checking if Odoo user can access the module directory..."
if [ -r "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py" ]; then
    echo "✓ Module manifest is readable"
else
    echo "✗ Module manifest is not readable by current user"
fi

# 6. Check if there are any missing dependencies referenced in the manifest
echo -e "\n6. Checking manifest dependencies..."
MANIFEST_DEPS=$(python3 -c "
import ast
with open('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py', 'r') as f:
    content = f.read()
manifest_dict = {}
exec(content, {'__builtins__': {}}, manifest_dict)
print('\\n'.join(manifest_dict.get('depends', [])))
")
echo "Dependencies listed in manifest:"
echo "$MANIFEST_DEPS"

# 7. Check if the __init__.py is properly structured for all subdirectories
echo -e "\n7. Checking __init__.py files structure..."
for init_file in /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__init__.py /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/models/__init__.py /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/wizard/__init__.py /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/reports/__init__.py; do
    if [ -f "$init_file" ]; then
        echo "✓ Found: $init_file"
        # Check if imports are syntactically valid
        python3 -m py_compile "$init_file" 2>/dev/null && echo "  ✓ $init_file syntax OK" || echo "  ✗ $init_file has syntax errors"
    else
        echo "✗ Missing: $init_file"
    fi
done

# 8. Check for potential conflicting installations or module naming
echo -e "\n8. Checking for module naming conflicts..."
CONFLICTING_MODULES=$(find /opt/instance1/odoo17 -type d -name "*l10n_th_account_tax*" -not -path "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/*" 2>/dev/null)
if [ -n "$CONFLICTING_MODULES" ]; then
    echo "⚠ Potential conflicting modules found:"
    echo "$CONFLICTING_MODULES"
else
    echo "✓ No conflicting module names found"
fi

# 9. Check if there are any duplicate module names in the addons path
if [ -f "/etc/odoo/odoo.conf" ]; then
    ADDONS_PATH=$(grep "^addons_path" /etc/odoo/odoo.conf | cut -d'=' -f2 | xargs)
    if [ -n "$ADDONS_PATH" ]; then
        echo -e "\n9. Checking for duplicate module names in addons path..."
        IFS=',' read -ra PATHS <<< "$ADDONS_PATH"
        for path in "${PATHS[@]}"; do
            path=$(echo $path | xargs)  # trim whitespace
            if [ -d "$path" ]; then
                duplicate_count=$(find "$path" -name "l10n_th_account_tax_report" -type d 2>/dev/null | wc -l)
                if [ "$duplicate_count" -gt 1 ]; then
                    echo "⚠ Found $duplicate_count instances of l10n_th_account_tax_report in addons path"
                    find "$path" -name "l10n_th_account_tax_report" -type d
                fi
            fi
        done
    fi
fi

# 10. Check if module name matches directory name
echo -e "\n10. Checking module naming consistency..."
MANIFEST_NAME=$(python3 -c "
import ast
with open('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py', 'r') as f:
    content = f.read()
manifest_dict = {}
exec(content, {'__builtins__': {}}, manifest_dict)
print(manifest_dict.get('name', 'NOT_FOUND'))
")
DIR_NAME=$(basename /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report)
echo "Manifest 'name' field: $MANIFEST_NAME"
echo "Directory name: $DIR_NAME"
echo "✓ Module name and directory name are not required to match, but directory name is what Odoo uses to identify the module"

echo -e "\n=== Deep Diagnostic Complete ==="

echo -e "\nMost likely causes for installation failure:"
echo "1. Odoo configuration doesn't include /opt/instance1/odoo17/custom-addons in addons_path"
echo "2. Odoo server has not been restarted after configuration changes"
echo "3. Required dependency modules are not installed"
echo "4. File permissions prevent Odoo server from reading the module files"
echo "5. Running Odoo processes are using old configuration"

echo -e "\nTo resolve:"
echo "1. Make sure Odoo config includes the module in addons_path"
echo "2. Fully stop all Odoo processes: pkill -f odoo"
echo "3. Start Odoo with the new configuration"
echo "4. Update Apps list in Odoo UI"