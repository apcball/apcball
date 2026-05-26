# -*- coding: utf-8 -*-

from . import controllers
from . import models
from . import wsgi_patch
wsgi_patch.post_load()