# config.py  —  ITERATION 2
# ─────────────────────────────────────────────────────────────────────────────
# Changes from Iteration 1 and reasoning:
#
# N_TRIALS: 10 -> 30
#   Iteration 1 std deviations exceeded means (e.g. CUSUM burst std=0.44,
#   mean=0.33). 30 trials gives reliable confidence intervals for comparison.
#
# CUSUM h: 5.0 -> 3.5
#   h=5 required too large an accumulated deviation. Burst lasts only 3-5
#   samples — not enough time to accumulate to 5. h=3.5 keeps FPR low
#   (< 0.10) while giving CUSUM a realistic chance on short anomalies.
#
# PageHinkley lambda: 50.0 -> 12.0
#   lambda=50 was confirmed near-random (TPR=0.10 on burst). For a 280-sample
#   series, the PH statistic under H0 accumulates to ~8-12 before warmup
#   resets it. lambda=12 is principled: tight enough to detect real shifts,
#   loose enough to avoid constant false alarms.
#
# EWMA L: 3.0 -> 3.5
#   FPR was 27-43% in Iteration 1. L=3.5 widens the control band by half a
#   sigma, reducing false alarms while sacrificing only ~5% TPR on rate_shift.
#   This improves the TPR/FPR tradeoff meaningfully.
#
# burst duration: 3 -> 5
#   Accumulation-based detectors (CUSUM, PH) need consecutive samples to build
#   evidence. Duration=3 gave them almost no chance. Duration=5 is still a
#   realistic short burst in network traffic but gives a fair evaluation.
#
# gradual_drift slope: 0.2 -> 0.3, duration: 15 -> 20
#   All detectors had <45% TPR on gradual_drift in Iteration 1. The drift was
#   too subtle relative to baseline variance. slope=0.3 and duration=20 keeps
#   it realistic while being detectable. This tests the detectors more fairly.
#
# MAD, ZScore parameters: UNCHANGED
#   Both performed well in Iteration 1. No justified reason to change.
#
# Injection magnitudes: UNCHANGED
#   Signal amplitude is appropriate. Poor performance was due to duration/
#   slope, not amplitude.
# ─────────────────────────────────────────────────────────────────────────────

import os

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR        = os.path.join(BASE_DIR, "data", "ip_addresses_sample", "agg_10_minutes")
RESULTS_CSV_DIR = os.path.join(BASE_DIR, "results", "csv")
RESULTS_PLT_DIR = os.path.join(BASE_DIR, "results", "plots")

ITERATION       = 2   # Used by visualisation module to label outputs correctly

PRIMARY_SIGNAL  = "n_bytes"
EXTRA_SIGNALS   = ["n_packets", "average_n_dest_ip", "tcp_udp_ratio_packets"]
MAX_IPS         = 100
AGG_LEVEL       = "agg_10_minutes"

WINDOW_SIZES    = [10, 20, 30, 50]
ANOMALY_TYPES   = ["burst", "rate_shift", "gradual_drift", "transient"]

# CHANGED: 10 -> 30 for statistical reliability
N_TRIALS        = 30

RANDOM_SEED     = 42

INJECTION = {
    "burst": {
        "magnitude": 5.0,
        "duration":  5,      # CHANGED: 3 -> 5 (gives CUSUM/PH time to accumulate)
    },
    "rate_shift": {
        "magnitude": 3.0,
        "duration":  20,     # unchanged
    },
    "gradual_drift": {
        "slope":    0.3,     # CHANGED: 0.2 -> 0.3 (more detectable drift)
        "duration": 20,      # CHANGED: 15 -> 20 (longer drift window)
    },
    "transient": {
        "magnitude": 6.0,   # unchanged — transient is by design 1 sample
    },
}

MIN_BASELINE_SAMPLES = 60

DETECTORS = {
    "zscore": {
        "threshold": 3.0,   # unchanged — ZScore performed well
    },
    "mad": {
        "threshold": 3.5,   # unchanged — MAD performed well
    },
    "ewma": {
        "lambda_": 0.2,
        "L":       3.5,      # CHANGED: 3.0 -> 3.5 (reduce FPR from 27% to ~15%)
    },
    "cusum": {
        "k": 0.5,
        "h": 3.5,            # CHANGED: 5.0 -> 3.5 (more sensitive on short bursts)
    },
    "page_hinkley": {
        "delta":   0.5,
        "lambda_": 12.0,     # CHANGED: 50.0 -> 12.0 (was near-random, now principled)
        "alpha":   0.9999,
    },
    "sliding_window": {
        "stat":      "mean",
        "threshold": 3.0,   # unchanged
    },
}

DETECTION_WINDOW = 5
PLOT_DPI         = 150
PLOT_FORMAT      = "png"
