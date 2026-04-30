"""
Phase 3 configuration — extends Phase 2's hyperparameters with ENSEMBLE settings.

Hyperparameters (DETECTORS, INJECTION, WINDOW_SIZES, ANOMALY_TYPES, N_TRIALS,
RANDOM_SEED, DATA_DIR) are sourced from Phase 2's config.py so that re-benchmark
results are directly comparable to Phase 2 row-for-row.

Phase 3 adds:
- ITERATION         = 3
- RESULTS_CSV_DIR / RESULTS_PLT_DIR pointing into Phase 3/results/
- ENSEMBLE          dict — confirmation gate + voting-layer composition
"""
import importlib.util
import os

import _phase2_bridge as _bridge   # ensures Phase 2 is on sys.path

# ---- Inherit Phase 2 config ------------------------------------------------
# Load Phase 2's config.py explicitly so it doesn't shadow Phase 3's own
# `import config` from elsewhere on the path.
_PHASE2_CONFIG_PATH = os.path.join(_bridge.PHASE2_ROOT, "config.py")
_spec = importlib.util.spec_from_file_location("phase2_config", _PHASE2_CONFIG_PATH)
_p2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_p2)

# Re-export Phase 2 values (verbatim — same hyperparameters, same dimensions)
DATA_DIR             = _p2.DATA_DIR
PRIMARY_SIGNAL       = _p2.PRIMARY_SIGNAL
EXTRA_SIGNALS        = _p2.EXTRA_SIGNALS
MAX_IPS              = _p2.MAX_IPS
AGG_LEVEL            = _p2.AGG_LEVEL
WINDOW_SIZES         = _p2.WINDOW_SIZES
ANOMALY_TYPES        = _p2.ANOMALY_TYPES
N_TRIALS             = _p2.N_TRIALS
RANDOM_SEED          = _p2.RANDOM_SEED
INJECTION            = _p2.INJECTION
MIN_BASELINE_SAMPLES = _p2.MIN_BASELINE_SAMPLES
DETECTORS            = _p2.DETECTORS
DETECTION_WINDOW     = _p2.DETECTION_WINDOW
PLOT_DPI             = _p2.PLOT_DPI
PLOT_FORMAT          = _p2.PLOT_FORMAT

# ---- Phase 3 overrides ------------------------------------------------------
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV_DIR = os.path.join(BASE_DIR, "results", "csv")
RESULTS_PLT_DIR = os.path.join(BASE_DIR, "results", "plots")

ITERATION = 3   # used by visualisation module to label outputs

# Cap each loaded series to this many samples before injection. None = no cap.
# CESNET 10-min series can be ~40,000 samples — cropping cuts smoke-run time
# without changing per-trial detection semantics (the injector picks a position
# in the middle 50% of whatever range it gets).
MAX_SAMPLES_PER_SERIES = None

# ---- Ensemble composition --------------------------------------------------
#   spike_layer.members      — base detector keys for the spike pipeline
#   sustained_layer.members  — base detector keys for the sustained-change pipeline
#   *_voting_mode            — "AND" (high precision) or "OR" (high recall)
#   confirmation_n           — gate fires only after this many consecutive child alarms
ENSEMBLE = {
    "confirmation_n": 2,
    "spike_layer": {
        "members":     ["mad", "zscore"],
        "voting_mode": "AND",
    },
    "sustained_layer": {
        "members":     ["ewma", "cusum"],
        "voting_mode": "OR",
    },
    "include_individual_baselines": True,   # re-benchmark each Phase 2 detector
    "include_gated_baselines":      True,   # also benchmark gated variants
    "include_or_variant":           True,   # include Spike_OR ablation
}
