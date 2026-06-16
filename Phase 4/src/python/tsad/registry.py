"""Detector registry -- the single source of truth for which detectors exist.

This file is the CONTRACT every detector implementation must satisfy:

  * Module path + class name are fixed here (the C twin uses the same slugs).
  * Each class subclasses ``tsad.core.base.Detector`` and accepts
    ``__init__(self, window=<int>, threshold=<float>, **params)``.
  * ``update(x) -> float`` returns a non-negative anomaly score; binary decision is
    ``score >= threshold``; warm-up returns 0.0.

``targets`` lists the anomaly type(s) the detector is designed to catch and drives the
condition->algorithm mapping (Q4). Imports are lazy so a single missing detector does not
break enumeration during incremental development.
"""

from __future__ import annotations

import importlib

# name -> (module, class, family, targets, default_params)
SPECS = {
    # ---- single detectors ----
    "ewma_z":          ("tsad.detectors.ewma_z",          "EwmaZ",
                        "statistical", ("spike", "drift", "transient"), {}),
    "robust_z":        ("tsad.detectors.robust_z",        "RobustZ",
                        "robust",      ("spike", "transient"), {}),
    "hampel":          ("tsad.detectors.hampel",          "Hampel",
                        "robust",      ("spike", "transient"), {}),
    "cusum":           ("tsad.detectors.cusum",           "Cusum",
                        "changepoint", ("drift",), {}),
    "page_hinkley":    ("tsad.detectors.page_hinkley",    "PageHinkley",
                        "changepoint", ("drift",), {}),
    "ewmv_adaptive":   ("tsad.detectors.ewmv_adaptive",   "EwmvAdaptive",
                        "statistical", ("spike", "drift"), {}),
    "deriv":           ("tsad.detectors.deriv",           "Deriv",
                        "derivative",  ("transient", "spike"), {}),
    "acf_periodicity": ("tsad.detectors.acf_periodicity", "AcfPeriodicity",
                        "spectral",    ("periodicity",), {}),
    "heavy_baseline":  ("tsad.detectors.heavy_baseline",  "HeavyBaseline",
                        "baseline_heavy", ("spike", "drift"), {}),
    # ---- combined / layered ----
    "layered":         ("tsad.ensembles.layered",         "Layered",
                        "ensemble", ("spike", "drift", "transient"), {}),
    "voting":          ("tsad.ensembles.voting",          "Voting",
                        "ensemble", ("spike", "drift", "transient", "periodicity"), {}),
    "cascade":         ("tsad.ensembles.cascade",         "Cascade",
                        "ensemble", ("spike", "drift", "transient"), {}),
}

SINGLE = [n for n, s in SPECS.items() if s[2] != "ensemble"]
ENSEMBLE = [n for n, s in SPECS.items() if s[2] == "ensemble"]


def get_class(name):
    module, cls, *_ = SPECS[name]
    mod = importlib.import_module(module)
    return getattr(mod, cls)


def make(name, window=30, **overrides):
    """Instantiate one detector."""
    cls = get_class(name)
    params = dict(SPECS[name][4])
    params.update(overrides)
    return cls(window=window, **params)


def make_factory(name, window=30, **overrides):
    """Return a zero-arg callable that builds a fresh detector (for timing/eval)."""
    return lambda: make(name, window=window, **overrides)


def all_names():
    return list(SPECS.keys())


def targets(name):
    return SPECS[name][3]


def family(name):
    return SPECS[name][2]
