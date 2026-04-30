"""
Phase 2 bridge — re-exports Phase 2 symbols for Phase 3.

Phase 2 lives at <repo>/Phase 2/ (note the space). To import across the folder
boundary we append Phase 2's root to sys.path. We deliberately keep Phase 3
src/-less (ensemble/ and evaluation/ live directly under Phase 3) so Phase 2's
`src/` is the only `src/` package on the path — `from src.detectors.base ...`
resolves unambiguously.

We APPEND (not insert) Phase 2 so that root-level module names that exist in
both projects (notably `config`) prefer Phase 3 when running from Phase 3.

Every Phase 3 module imports from `_phase2_bridge`, never directly from
`src.detectors.*`. The path manipulation lives only here.
"""
import os
import sys

_HERE        = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT   = os.path.dirname(_HERE)
PHASE2_ROOT  = os.path.join(_REPO_ROOT, "Phase 2")

if not os.path.isdir(PHASE2_ROOT):
    raise RuntimeError(
        f"Phase 2 directory not found at {PHASE2_ROOT}. "
        "Phase 3 expects a sibling 'Phase 2' folder under the same Code/ root."
    )

if PHASE2_ROOT not in sys.path:
    sys.path.append(PHASE2_ROOT)

from src.detectors.base                  import DetectorBase, DetectionResult
from src.detectors.zscore                import ZScoreDetector
from src.detectors.mad                   import MADDetector
from src.detectors.ewma                  import EWMADetector
from src.detectors.cusum                 import CUSUMDetector
from src.detectors.page_hinkley          import PageHinkleyDetector
from src.detectors.sliding_window_stats  import SlidingWindowStatsDetector
from src.pipeline.window_buffer          import WindowBuffer
from src.pipeline.loader                 import load_cesnet_sample
from src.injector.anomaly_injector       import AnomalyInjector, InjectionResult
from src.evaluation.metrics              import compute_metrics, aggregate_metrics, EvalMetrics

__all__ = [
    "PHASE2_ROOT",
    "DetectorBase", "DetectionResult",
    "ZScoreDetector", "MADDetector", "EWMADetector",
    "CUSUMDetector", "PageHinkleyDetector", "SlidingWindowStatsDetector",
    "WindowBuffer", "load_cesnet_sample",
    "AnomalyInjector", "InjectionResult",
    "compute_metrics", "aggregate_metrics", "EvalMetrics",
]
