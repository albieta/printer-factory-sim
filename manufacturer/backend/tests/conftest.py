from __future__ import annotations

import sys
from pathlib import Path


for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
