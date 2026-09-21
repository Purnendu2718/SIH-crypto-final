import os
import sys
import importlib.util

_services = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend", "app", "services"))
_tests = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend", "tests"))
for p in (_services, _tests):
    if p not in sys.path:
        sys.path.insert(0, p)

_spec = importlib.util.spec_from_file_location(
    "backend_tests_validator",
    os.path.join(_tests, "test_validator.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Expose test classes into this namespace so standard unittest discovers them
for _k, _v in list(_mod.__dict__.items()):
    if isinstance(_v, type) and issubclass(_v, _mod.unittest.TestCase):
        globals()[_k] = _v

def load_tests(loader, standard_tests, pattern):
    return loader.loadTestsFromModule(_mod)

if __name__ == "__main__":
    import unittest
    unittest.main()
