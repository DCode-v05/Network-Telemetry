
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

    double mu, var, sd, g_pos, g_neg, xbar, m_up, min_up, m_dn, min_dn, z, mu_s,
           sigma, x_prev, mu_d, var_d, r_ref;
    int period;

    double buf[TSAD_MAXW];
    int head, count;
} TsadDetector;

void   tsad_init(TsadDetector *d, TsadKind kind, int window);
void   tsad_reset(TsadDetector *d);
double tsad_update(TsadDetector *d, double x);
int    tsad_state_bytes(TsadKind kind, int window);
int    tsad_kind_from_slug(const char *slug);
const char *tsad_slug(TsadKind kind);

#ifdef __cplusplus
}
#endif

#endif
