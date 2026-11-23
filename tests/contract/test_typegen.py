import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("npx") is None, reason="TypeScript contract check requires npx")
def test_typegen_compiles_all_captured_responses():
    script = Path(__file__).with_name("typegen") / "check.py"
    subprocess.run([sys.executable, str(script)], check=True)
