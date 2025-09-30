# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

# Import compatibility layer
from . import hooks

# Import main modules with error handling for Odoo 17
try:
    from . import models
except ImportError as e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.warning(f"Failed to import models: {e}")

try:
    from . import wizard
except ImportError as e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.warning(f"Failed to import wizard: {e}")

try:
    from . import reports
except ImportError as e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.warning(f"Failed to import reports: {e}")

# Use compatibility hooks
pre_init_hook = hooks.pre_init_hook
post_init_hook = hooks.post_init_hook
uninstall_hook = hooks.uninstall_hook
