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

import _phase2_bridge as _bridge

_PHASE2_CONFIG_PATH = os.path.join(_bridge.PHASE2_ROOT, "config.py")
_spec = importlib.util.spec_from_file_location("phase2_config", _PHASE2_CONFIG_PATH)
_p2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_p2)

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

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV_DIR = os.path.join(BASE_DIR, "results", "csv")
RESULTS_PLT_DIR = os.path.join(BASE_DIR, "results", "plots")

ITERATION = 3

MAX_SAMPLES_PER_SERIES = None

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
    "include_individual_baselines": True,
    "include_gated_baselines":      True,
    "include_or_variant":           True,
}
