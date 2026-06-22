#!/usr/bin/env bash
set -euo pipefail

# ─── Odoo Module Scaffold Script ──────────────────────────
# Usage: ./scaffold.sh <module_name> [--name "Display Name"] [--depends base,sale] [--model buz.model.name]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# ─── Parse args ────────────────────────────────────────────
MODULE_NAME=""
DISPLAY_NAME=""
DEPENDS="base"
MODEL_NAME=""

while [ $# -gt 0 ]; do
    case "$1" in
        --name)    DISPLAY_NAME="$2"; shift 2 ;;
        --depends) DEPENDS="$2"; shift 2 ;;
        --model)   MODEL_NAME="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 <module_name> [--name \"Display Name\"] [--depends base,sale] [--model buz.model.name]"
            exit 0
            ;;
        *)
            if [ -z "$MODULE_NAME" ]; then
                MODULE_NAME="$1"; shift
            else
                echo "❌ Unexpected argument: $1"
                exit 1
            fi
            ;;
    esac
done

if [ -z "$MODULE_NAME" ]; then
    echo "❌ Error: specify module name"
    echo "Usage: $0 <module_name> [--name \"Display Name\"] [--depends base,sale] [--model buz.model.name]"
    exit 1
fi

if [ -z "$DISPLAY_NAME" ]; then
    DISPLAY_NAME="$(echo "$MODULE_NAME" | sed 's/_/ /g' | sed 's/\b\(.\)/\u\1/g')"
fi

MODULE_DIR="$PROJECT_ROOT/$MODULE_NAME"

if [ -d "$MODULE_DIR" ]; then
    echo "❌ Module already exists: $MODULE_DIR"
    exit 1
fi

# ─── Create structure ─────────────────────────────────────
echo "📁 Creating $MODULE_NAME..."
mkdir -p "$MODULE_DIR"/{models,views,security,data,wizard,report,tests}

# ─── __manifest__.py ──────────────────────────────────────
DEPENDS_PY="    'depends': ["
IFS=',' read -ra DEPS <<< "$DEPENDS"
for d in "${DEPS[@]}"; do
    DEPENDS_PY="$DEPENDS_PY
        '$d',"
done
DEPENDS_PY="$DEPENDS_PY
    ],"

cat > "$MODULE_DIR/__manifest__.py" <<MANIFEST
{
    'name': '$DISPLAY_NAME',
    'version': '17.0.1.0.0',
    'category': 'Custom',
    'summary': 'TODO: add summary',
    'description': '''
TODO: add module description
    ''',
    'author': 'Mogen Co., Ltd.',
    'website': 'https://mogth.work',
    'license': 'LGPL-3',
    $DEPENDS_PY
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/${MODULE_NAME}_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
MANIFEST

# ─── __init__.py ───────────────────────────────────────────
touch "$MODULE_DIR/__init__.py"

# ─── models/__init__.py ───────────────────────────────────
touch "$MODULE_DIR/models/__init__.py"

# ─── views ─────────────────────────────────────────────────
cat > "$MODULE_DIR/views/${MODULE_NAME}_views.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<odoo>

</odoo>
XML

# ─── security ──────────────────────────────────────────────
cat > "$MODULE_DIR/security/ir.model.access.csv" <<CSV
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
CSV

cat > "$MODULE_DIR/security/security.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<odoo>

</odoo>
XML

# ─── data / wizard / report / tests ────────────────────────
touch "$MODULE_DIR/data/.gitkeep"
echo "" > "$MODULE_DIR/wizard/__init__.py"
echo "" > "$MODULE_DIR/wizard/.gitkeep"
echo "" > "$MODULE_DIR/report/__init__.py"
echo "" > "$MODULE_DIR/report/.gitkeep"

cat > "$MODULE_DIR/tests/__init__.py" <<PY
from . import test_${MODULE_NAME}
PY

cat > "$MODULE_DIR/tests/test_${MODULE_NAME}.py" <<PY
from odoo.tests import common


class Test${DISPLAY_NAME// /}(common.TransactionCase):

    def setUp(self):
        super().setUp()
        # TODO: setup test data

    def test_something(self):
        # TODO: write test
        pass
PY

# ─── Model file (if --model provided) ──────────────────────
if [ -n "$MODEL_NAME" ]; then
    # Convert buz.test.scaffold -> BuzTestScaffold
    MODEL_CLASS=""
    IFS='.' read -ra PARTS <<< "$MODEL_NAME"
    for part in "${PARTS[@]}"; do
        first=$(echo "$part" | cut -c1 | tr '[:lower:]' '[:upper:]')
        rest=$(echo "$part" | cut -c2-)
        MODEL_CLASS="${MODEL_CLASS}${first}${rest}"
    done

    cat > "$MODULE_DIR/models/${MODULE_NAME}.py" <<PY
from odoo import api, fields, models


class ${MODEL_CLASS}(models.Model):
    _name = '$MODEL_NAME'
    _description = '${DISPLAY_NAME}'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company = True

    name = fields.Char(string='Name', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        check_company=True,
    )
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Name must be unique per company!'),
    ]
PY

    # Update models/__init__.py
    echo "from . import ${MODULE_NAME}" >> "$MODULE_DIR/models/__init__.py"

    # Create menu XML
    cat > "$MODULE_DIR/views/${MODULE_NAME}_menus.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- Actions -->
    <record id="action_${MODULE_NAME}" model="ir.actions.act_window">
        <field name="name">${DISPLAY_NAME}</field>
        <field name="res_model">${MODEL_NAME}</field>
        <field name="view_mode">tree,form</field>
    </record>

    <!-- Menu -->
    <menuitem id="menu_${MODULE_NAME}" name="${DISPLAY_NAME}" action="action_${MODULE_NAME}" sequence="10"/>

</odoo>
XML

    # Update manifest data
    python3 -c "
with open('$MODULE_DIR/__manifest__.py', 'r') as f:
    content = f.read()
content = content.replace(
    \"'views/${MODULE_NAME}_views.xml',\",
    \"'views/${MODULE_NAME}_views.xml',\\n        'views/${MODULE_NAME}_menus.xml',\"
)
with open('$MODULE_DIR/__manifest__.py', 'w') as f:
    f.write(content)
" 2>/dev/null || true

    # Update security CSV with model access
    MODEL_SAFE="${MODEL_NAME//./_}"
    cat > "$MODULE_DIR/security/ir.model.access.csv" <<CSV
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_${MODULE_NAME}_user,${MODULE_NAME}.user,model_${MODEL_SAFE},base.group_user,1,1,1,1
CSV
fi

# ─── Done ──────────────────────────────────────────────────
echo ""
echo "✅ Module scaffolded: $MODULE_DIR"
echo ""
echo "Next steps:"
echo "  1. cd $MODULE_NAME"
echo "  2. Edit __manifest__.py — update depends, add data files"
echo "  3. Implement models/ and views/"
echo "  4. git add $MODULE_NAME && git commit"
echo ""
