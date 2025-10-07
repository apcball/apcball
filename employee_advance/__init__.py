from . import models
from . import wizards
from . import hooks

# Make the hooks available at the package level
pre_init_hook = hooks.pre_init_hook
post_init_hook = hooks.post_init_hook