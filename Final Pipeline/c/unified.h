/* unified.h -- C99 twin of the `unified` streaming anomaly detector.
 *
 * Standalone port of the Phase 4 Python `Unified` detector (one <100-byte unit
 * covering spike / drift / periodicity-loss / transient via three MAX-fused
 * heads). Same contract as the research repo's C twin:
 *
 *     unified_init(d, window);
 *     score = unified_update(d, x);      // one sample in, one score out
 *     bytes = unified_state_bytes();     // float32 deployment footprint
 *
 * Numerics: the COMPUTE path is double precision so it matches the float64
 * Python reference to <= 1e-4 (verified by parity_check). The <100-byte figure
 * reported by unified_state_bytes() is the on-device float32 STATE model
 * (5 scalars + 17-deep ring buffer + int counters = 96 bytes); compute precision
 * and deployment footprint are decoupled by design, exactly as in tsad.c.
 */
#ifndef UNIFIED_H
#define UNIFIED_H

#ifdef __cplusplus
extern "C" {
#endif

#define UNIFIED_BUF_LEN 17   /* shared ring buffer depth (spans the dominant period) */

typedef struct {
    /* configuration / derived constants (set once in unified_init) */
    int    window;
    int    warmup;
    double threshold;        /* fusion decision boundary (1.0); scoring is threshold-free */
    double alpha;            /* derivative-head EWMA rate  = 2/(window+1) */
    double lam;              /* drift-head fast EWMA rate   = 2/(window+1) */
    double alpha_s;          /* drift-head slow baseline rate = lam/4 */

    /* counters */
    int    n;                /* samples seen (drives warm-up) */

    /* head 1 -- derivative z-score state */
    double mu_d, var_d;

    /* head 2 -- EWMA control-chart state */
    double z, mu;

    /* head 3 -- gated ACF-drop state */
    int    period;           /* locked lag (int, so it costs no float in the model) */
    int    armed;            /* 1 once an established periodicity is detected */
    double r_ref;            /* reference autocorrelation at `period` */

    /* shared ring buffer (mirrors a C float buf[N]; int head, count;) */
    double buf[UNIFIED_BUF_LEN];
    int    head, count;

    double last_score;
    double s_drv, s_drift, s_per;   /* last per-head normalised scores (introspection) */
} UnifiedDetector;

void   unified_init(UnifiedDetector *d, int window);
void   unified_reset(UnifiedDetector *d);
double unified_update(UnifiedDetector *d, double x);
int    unified_state_bytes(void);   /* float32 model: 5*4 + 17*4 + 8 = 96 */

#ifdef __cplusplus
}
#endif

#endif /* UNIFIED_H */
