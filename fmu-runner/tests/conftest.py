"""
conftest.py — adds fmu-runner root to sys.path so that pytest can resolve
`import main` and `import auth` regardless of from which directory pytest
is invoked, as long as the working directory is fmu-runner/ or any parent.
"""

import sys
import os

# Ensure the fmu-runner directory (parent of this tests/ dir) is on sys.path
FMU_RUNNER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FMU_RUNNER_ROOT not in sys.path:
    sys.path.insert(0, FMU_RUNNER_ROOT)
