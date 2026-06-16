import os
import sys
import logging
import argparse

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Phase 2 Iteration 2 - Network Telemetry Anomaly Detection"
    )
    parser.add_argument("--signal",  default=None)
    parser.add_argument("--max_ips", type=int, default=None)
    parser.add_argument("--no_plot", action="store_true")
    parser.add_argument(
        "--no_dashboard",
        action="store_true",
        help="Skip generating the interactive HTML dashboard after evaluation",
    )
    parser.add_argument(
        "--iter1_csv",
        default=None,
        help="Path to Iteration 1 aggregated_results.csv for side-by-side comparison plots"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    import config as cfg
    if args.signal:
        cfg.PRIMARY_SIGNAL = args.signal
    if args.max_ips:
        cfg.MAX_IPS = args.max_ips

    logger.info("=" * 60)
    logger.info(f"  Phase 2 — Iteration {cfg.ITERATION}")
    logger.info(f"  Signal       : {cfg.PRIMARY_SIGNAL}")
    logger.info(f"  Window sizes : {cfg.WINDOW_SIZES}")
    logger.info(f"  Anomaly types: {cfg.ANOMALY_TYPES}")
    logger.info(f"  Trials/combo : {cfg.N_TRIALS}  (Iter1 was 10)")
    logger.info(f"  Max IPs      : {cfg.MAX_IPS}")
    logger.info("  Key changes vs Iter 1:")
    logger.info("    N_TRIALS 10->30 | CUSUM h 5.0->3.5 | PH lambda 50->12")
    logger.info("    EWMA L 3.0->3.5 | burst dur 3->5 | drift slope 0.2->0.3")
    logger.info("=" * 60)

    if not os.path.isdir(cfg.DATA_DIR):
        logger.error(
            f"\nData directory not found: {cfg.DATA_DIR}\n"
            "Make sure DATA_DIR in config.py points to agg_10_minutes/\n"
            "inside ip_addresses_sample. See the root README.md."
        )
        sys.exit(1)

    from src.evaluation.harness import run_evaluation
    aggregated = run_evaluation()

    _print_summary(aggregated)

    if not args.no_plot:
        try:
            from src.evaluation.visualise import Visualiser, compare_iterations

            v2 = Visualiser(
                results_csv_dir = cfg.RESULTS_CSV_DIR,
                plots_dir       = cfg.RESULTS_PLT_DIR,
                iteration       = cfg.ITERATION,
            )
            v2.run_all()

            if args.iter1_csv and os.path.exists(args.iter1_csv):
                compare_dir = os.path.join(os.path.dirname(cfg.RESULTS_PLT_DIR), "comparison_plots")
                compare_iterations(
                    csv_iter1 = args.iter1_csv,
                    csv_iter2 = os.path.join(cfg.RESULTS_CSV_DIR, "aggregated_results.csv"),
                    out_dir   = compare_dir,
                )
            elif args.iter1_csv:
                logger.warning(f"Iter1 CSV not found at {args.iter1_csv} — comparison skipped.")
            else:
                logger.info(
                    "Tip: run with --iter1_csv path/to/iter1/aggregated_results.csv "
                    "to generate side-by-side comparison plots."
                )

        except Exception as e:
            logger.warning(f"Visualisation failed: {e}. Results are in results/csv/")

    if not args.no_dashboard:
        try:
            import plotly
            from dashboard.generate_report import generate
            generate()
            logger.info("Dashboard -> results/dashboard.html")
        except ImportError:
            logger.warning(
                "Plotly not installed — skipping dashboard. "
                "Run: pip install plotly>=5.18"
            )
        except Exception as e:
            logger.warning(f"Dashboard generation failed: {e}. Run: python dashboard/generate_report.py")

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
    print("\n" + "=" * 82)
    print(f"  {'DETECTOR':<32} {'ANOMALY':<16} {'WIN':>4}  "
          f"{'F1':>6}  {'TPR':>6}  {'FPR':>6}  {'DET%':>6}")
    print("  " + "-" * 78)
    for row in aggregated:
        dr = row.get("detection_rate", 0)
        print(
            f"  {row.get('detector',''):<32} "
            f"{row.get('anomaly_type',''):<16} "
            f"{row.get('window_size',0):>4}  "
            f"{row.get('f1_mean',0.0):>6.3f}  "
            f"{row.get('tpr_mean',0.0):>6.3f}  "
            f"{row.get('fpr_mean',0.0):>6.3f}  "
            f"{dr*100:>5.0f}%"
        )
    print("=" * 82 + "\n")


if __name__ == "__main__":
    main()
