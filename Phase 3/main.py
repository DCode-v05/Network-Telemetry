"""
Phase 3 entry point.

Runs the expanded benchmark (~14 detectors per window), saves CSVs into
Phase 3/results/csv/, optionally renders plots and the Phase 3 dashboard.
"""
import argparse
import logging
import os
import sys

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Phase 3 — Two-Layer Ensemble Anomaly Detection"
    )
    parser.add_argument("--signal",  default=None)
    parser.add_argument("--max_ips", type=int, default=None)
    parser.add_argument("--no_plot",      action="store_true")
    parser.add_argument("--no_dashboard", action="store_true")
    parser.add_argument(
        "--compare_phase2_csv",
        default=None,
        help=("Path to Phase 2 aggregated_results.csv for side-by-side bars in "
              "the Phase 3 dashboard. Defaults to ../Phase 2/results/csv/"
              "aggregated_results.csv if it exists."),
    )
    parser.add_argument(
        "--confirmation_n",
        type=int,
        default=None,
        help="Override ENSEMBLE.confirmation_n for ablation runs.",
    )
    parser.add_argument(
        "--n_trials",
        type=int,
        default=None,
        help="Override N_TRIALS (useful for smoke runs).",
    )
    parser.add_argument(
        "--window_sizes",
        type=int,
        nargs="+",
        default=None,
        help="Override WINDOW_SIZES, e.g. --window_sizes 20",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Smoke-run shortcut: max_ips=10, n_trials=3, window_sizes=[20], "
             "max_samples=2000.",
    )
    parser.add_argument(
        "--max_samples",
        type=int,
        default=None,
        help="Cap each loaded series to this many samples (no cap by default).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    PHASE3_ROOT = os.path.dirname(os.path.abspath(__file__))
    if PHASE3_ROOT not in sys.path:
        sys.path.insert(0, PHASE3_ROOT)

    import config as cfg

    if args.quick:
        cfg.MAX_IPS                = 10
        cfg.N_TRIALS               = 3
        cfg.WINDOW_SIZES           = [20]
        cfg.MAX_SAMPLES_PER_SERIES = 2000

    if args.max_samples is not None:
        cfg.MAX_SAMPLES_PER_SERIES = args.max_samples

    if args.signal:
        cfg.PRIMARY_SIGNAL = args.signal
    if args.max_ips:
        cfg.MAX_IPS = args.max_ips
    if args.n_trials is not None:
        cfg.N_TRIALS = args.n_trials
    if args.window_sizes is not None:
        cfg.WINDOW_SIZES = args.window_sizes
    if args.confirmation_n is not None:
        if args.confirmation_n < 1:
            logger.error("--confirmation_n must be >= 1")
            sys.exit(1)
        cfg.ENSEMBLE["confirmation_n"] = args.confirmation_n

    if args.compare_phase2_csv is None:
        default_p2 = os.path.normpath(os.path.join(
            PHASE3_ROOT, "..", "Phase 2", "results", "csv", "aggregated_results.csv"
        ))
        if os.path.isfile(default_p2):
            args.compare_phase2_csv = default_p2

    logger.info("=" * 64)
    logger.info(f"  Phase 3 — Iteration {cfg.ITERATION}")
    logger.info(f"  Signal           : {cfg.PRIMARY_SIGNAL}")
    logger.info(f"  Window sizes     : {cfg.WINDOW_SIZES}")
    logger.info(f"  Anomaly types    : {cfg.ANOMALY_TYPES}")
    logger.info(f"  Trials/combo     : {cfg.N_TRIALS}")
    logger.info(f"  Max IPs          : {cfg.MAX_IPS}")
    logger.info(f"  confirmation_n   : {cfg.ENSEMBLE['confirmation_n']}")
    logger.info(f"  spike layer      : {cfg.ENSEMBLE['spike_layer']['voting_mode']}"
                f" of {cfg.ENSEMBLE['spike_layer']['members']}")
    logger.info(f"  sustained layer  : {cfg.ENSEMBLE['sustained_layer']['voting_mode']}"
                f" of {cfg.ENSEMBLE['sustained_layer']['members']}")
    logger.info("=" * 64)

    if not os.path.isdir(cfg.DATA_DIR):
        logger.error(
            f"\nData directory not found: {cfg.DATA_DIR}\n"
            "Phase 3 reads CESNET data from Phase 2's data/ folder. Make sure\n"
            "Phase 2/data/ip_addresses_sample/agg_10_minutes/ contains the CSVs."
        )
        sys.exit(1)

    from evaluation.harness import run_evaluation
    aggregated = run_evaluation()

    _print_summary(aggregated)

    if not args.no_plot:
        try:
            from _phase2_bridge import PHASE2_ROOT
            from src.evaluation.visualise import Visualiser
            v = Visualiser(
                results_csv_dir = cfg.RESULTS_CSV_DIR,
                plots_dir       = cfg.RESULTS_PLT_DIR,
                iteration       = cfg.ITERATION,
            )
            v.run_all()
        except Exception as e:
            logger.warning(f"Visualisation failed: {e}. Results are in {cfg.RESULTS_CSV_DIR}/")

    if not args.no_dashboard:
        try:
            import plotly
            from dashboard.generate_report import generate
            generate(compare_phase2_csv=args.compare_phase2_csv)
            logger.info(f"Dashboard -> {os.path.join(PHASE3_ROOT, 'results', 'dashboard.html')}")
        except ImportError:
            logger.warning("Plotly not installed — skipping dashboard.")
        except Exception as e:
            logger.warning(f"Dashboard generation failed: {e}.")

        try:
            from dashboard.export_data import main as export_react_data
            export_react_data()
            logger.info("React dashboard data -> dashboard/web/src/data.json "
                        "(rebuild with: cd dashboard/web && npm run build)")
        except Exception as e:
            logger.warning(f"React data export skipped: {e}")

    logger.info(f"Done. Results in {cfg.RESULTS_CSV_DIR}/")


def _print_summary(aggregated):
    if not aggregated:
        return
    print("\n" + "=" * 90)
    print(f"  {'DETECTOR':<40} {'ANOMALY':<16} {'WIN':>4}  "
          f"{'F1':>6}  {'TPR':>6}  {'FPR':>6}  {'DET%':>6}")
    print("  " + "-" * 86)
    for row in aggregated:
        dr = row.get("detection_rate", 0)
        print(
            f"  {row.get('detector',''):<40} "
            f"{row.get('anomaly_type',''):<16} "
            f"{row.get('window_size',0):>4}  "
            f"{row.get('f1_mean',0.0):>6.3f}  "
            f"{row.get('tpr_mean',0.0):>6.3f}  "
            f"{row.get('fpr_mean',0.0):>6.3f}  "
            f"{dr*100:>5.0f}%"
        )
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
