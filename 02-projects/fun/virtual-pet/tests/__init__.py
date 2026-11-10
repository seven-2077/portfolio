"""让 `python -m unittest discover -s tests` 在任何调用方式下都能找到 pet 包。"""

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
