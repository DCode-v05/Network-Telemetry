/* tsad.h -- portable C99 streaming anomaly detectors (on-device twin).
 *
 * Nine streaming detectors ported line-for-line from the Phase 4 Python
 * reference (tsad/detectors). All compute is done in DOUBLE precision so
 * the C output matches the float64 Python reference to < 1e-4.
 *
 * The TsadDetector struct is a deliberate "fat union": it carries every scalar
 * any detector needs (all double) plus a fixed ring buffer. sizeof(struct) is
 * therefore large -- that is fine. The HONEST per-detector float32 deployment
 * footprint is what tsad_state_bytes() returns, matching the Python
 * Detector.state_bytes accounting (state_floats*4 + buffer_len*4 + 8).
 */
#ifndef TSAD_H
#define TSAD_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    TSAD_EWMA_Z = 0,
    TSAD_ROBUST_Z,
    TSAD_HAMPEL,
    TSAD_CUSUM,
    TSAD_PAGE_HINKLEY,
    TSAD_EWMV_ADAPTIVE,
    TSAD_DERIV,
    TSAD_ACF,
    TSAD_HEAVY,
    TSAD_KIND_COUNT
} TsadKind;

#define TSAD_MAXW 64

typedef struct {
    TsadKind kind;
    int window, n, warmup;
    double threshold, alpha;

    /* union-style: ALL fields any detector needs, all double */
    double mu, var, sd, g_pos, g_neg, xbar, m_up, min_up, m_dn, min_dn, z, mu_s,
           sigma, x_prev, mu_d, var_d, r_ref;
    int period;

    double buf[TSAD_MAXW];
    int head, count;
} TsadDetector;

void   tsad_init(TsadDetector *d, TsadKind kind, int window);
void   tsad_reset(TsadDetector *d);
double tsad_update(TsadDetector *d, double x);   /* returns the anomaly score */
int    tsad_state_bytes(TsadKind kind, int window); /* float32 deployment footprint */
int    tsad_kind_from_slug(const char *slug);    /* returns TsadKind or -1 */
const char *tsad_slug(TsadKind kind);

#ifdef __cplusplus
}
#endif

#endif /* TSAD_H */
