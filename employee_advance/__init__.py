from . import models
from . import wizards
from . import hooks

# Make the post_init_hook available at the package level
post_init_hook = hooks.post_init_hook