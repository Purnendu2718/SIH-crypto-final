import os
import sys

_services = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend", "app", "services"))
if _services not in sys.path:
    sys.path.insert(0, _services)

from address_validator import *
