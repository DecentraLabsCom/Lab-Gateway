"""
conftest.py — adds fmu-runner root to sys.path so that pytest can resolve
`import main` and `import auth` regardless of from which directory pytest
is invoked, as long as the working directory is fmu-runner/ or any parent.
"""

import sys
import os

# Existing unit tests exercise the native backend; make that opt-in explicit in
# the test environment rather than inheriting the production-safe defaults.
os.environ.setdefault("FMU_BACKEND_MODE", "local")
os.environ.setdefault("FMU_LOCAL_DEV_MODE", "true")
os.environ.setdefault("FMU_LOCAL_REALTIME_ENABLED", "true")
os.environ.setdefault("AAS_ALLOWED_HOSTS", "127.0.0.1,basyx-mock,basyx-test")
os.environ.setdefault("AAS_SERVICE_TOKEN", "test-aas-service-token")

# Ensure the fmu-runner directory (parent of this tests/ dir) is on sys.path
FMU_RUNNER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FMU_RUNNER_ROOT not in sys.path:
    sys.path.insert(0, FMU_RUNNER_ROOT)
