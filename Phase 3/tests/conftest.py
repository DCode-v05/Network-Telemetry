"""
Phase 3 pytest bootstrap.

Adds Phase 3 root to sys.path so test modules can import the bridge, the
ensemble package, and the local _helpers module without package gymnastics.

MockDetector lives in `tests/_helpers.py` (not here) — pytest does not expose
conftest.py as an importable module, so test bodies cannot do
`from conftest import ...`.
"""
import os
import sys

_PHASE3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PHASE3_ROOT not in sys.path:
    sys.path.insert(0, _PHASE3_ROOT)

import _phase2_bridge
