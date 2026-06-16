
import os

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR        = os.path.join(BASE_DIR, "data", "ip_addresses_sample", "agg_10_minutes")
RESULTS_CSV_DIR = os.path.join(BASE_DIR, "results", "csv")
RESULTS_PLT_DIR = os.path.join(BASE_DIR, "results", "plots")

ITERATION       = 2

PRIMARY_SIGNAL  = "n_bytes"
EXTRA_SIGNALS   = ["n_packets", "average_n_dest_ip", "tcp_udp_ratio_packets"]
MAX_IPS         = 100
AGG_LEVEL       = "agg_10_minutes"

WINDOW_SIZES    = [10, 20, 30, 50]
ANOMALY_TYPES   = ["burst", "rate_shift", "gradual_drift", "transient"]

N_TRIALS        = 30

RANDOM_SEED     = 42

INJECTION = {
    "burst": {
        "magnitude": 5.0,
        "duration":  5,
    },
    "rate_shift": {
        "magnitude": 3.0,
        "duration":  20,
    },
    "gradual_drift": {
        "slope":    0.3,
        "duration": 20,
    },
    "transient": {
        "magnitude": 6.0,
    },
}

MIN_BASELINE_SAMPLES = 60

DETECTORS = {
    "zscore": {
        "threshold": 3.0,
    },
    "mad": {
        "threshold": 3.5,
    },
    "ewma": {
        "lambda_": 0.2,
        "L":       3.5,
    },
    "cusum": {
        "k": 0.5,
        "h": 3.5,
    },
    "page_hinkley": {
        "delta":   0.5,
        "lambda_": 12.0,
        "alpha":   0.9999,
    },
    "sliding_window": {
        "stat":      "mean",
        "threshold": 3.0,
    },
}

DETECTION_WINDOW = 5
PLOT_DPI         = 150
PLOT_FORMAT      = "png"
