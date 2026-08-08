from __future__ import annotations

import sys
from pathlib import Path

MODELS_TEST_DIR = Path(__file__).resolve().parent / "models"
if str(MODELS_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_TEST_DIR))
