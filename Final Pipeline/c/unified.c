/* unified.c -- C99 twin of the `unified` streaming anomaly detector.
 *
 * Ported line-for-line from Phase 4/src/python/tsad/ensembles/unified.py so the
 * two produce identical scores (parity_check asserts <= 1e-4). Pure scalar
 * arithmetic; O(BUF) per sample with a one-time lag scan when the buffer fills.
 */
#include "unified.h"

#include <math.h>

/* tuning constants -- identical to the Python Unified class */
#define U_GATE    0.45   /* min autocorrelation to arm the periodicity head */
#define U_TH_DRV  2.8    /* derivative-head normaliser */
#define U_TH_EWMV 2.5    /* drift-head normaliser */
#define U_DR_CAP  0.9    /* drift-head output clip (< 1.0) */
#define U_TH_PER  0.4    /* periodicity-head normaliser */
#define U_HOLD    2.5    /* freeze derivative baseline while |z_deriv| exceeds this */
#define U_EPS     1e-9

void unified_reset(UnifiedDetector *d)
{
    int i;
    d->n = 0;
    d->last_score = 0.0;
    for (i = 0; i < UNIFIED_BUF_LEN; i++)
        d->buf[i] = 0.0;
    d->head = 0;
    d->count = 0;
    d->period = 0;
    d->r_ref = 0.0;
    d->armed = 0;
    d->mu_d = 0.0;
    d->var_d = 1.0;
    d->z = 0.0;
    d->mu = 0.0;
    /* derived constants (recomputed from window, mirrors Python reset) */
    d->alpha = 2.0 / (d->window + 1);
    d->lam = 2.0 / (d->window + 1);
    d->alpha_s = d->lam / 4.0;
}

void unified_init(UnifiedDetector *d, int window)
{
    if (window < 1)
        window = 1;
    d->window = window;
    d->threshold = 1.0;
    d->warmup = window / 3;
    if (d->warmup < 3)
        d->warmup = 3;
    unified_reset(d);
}

/* lag-`lag` autocorrelation of vals[0..N) with precomputed mean/den */
static double u_acf(const double *vals, int N, int lag, double mean, double den)
{
    int i;
    double num = 0.0;
    if (N <= lag + 2 || den < U_EPS)
        return 0.0;
    for (i = lag; i < N; i++)
        num += (vals[i] - mean) * (vals[i - lag] - mean);
    return num / den;
}

double unified_update(UnifiedDetector *d, double x)
{
    double vals[UNIFIED_BUF_LEN];
    int m, i, idx, warm;
    double mean, den, var, sd, dx, z_deriv, diff, s_drv;
    double control_sigma, s_ewmv, s_drift, s_per, score;

    d->n += 1;

    /* ring push */
    d->buf[d->head] = x;
    d->head = (d->head + 1) % UNIFIED_BUF_LEN;
    if (d->count < UNIFIED_BUF_LEN)
        d->count += 1;

    warm = (d->n > d->warmup);

    /* materialise values oldest -> newest */
    m = d->count;
    if (d->count < UNIFIED_BUF_LEN) {
        for (i = 0; i < d->count; i++)
            vals[i] = d->buf[i];
    } else {
        idx = 0;
        for (i = d->head; i < UNIFIED_BUF_LEN; i++)
            vals[idx++] = d->buf[i];
        for (i = 0; i < d->head; i++)
            vals[idx++] = d->buf[i];
    }

    if (m == 1) {
        d->z = x;
        d->mu = x;
        d->last_score = 0.0;
        return 0.0;
    }

    /* shared windowed mean / variance */
    mean = 0.0;
    for (i = 0; i < m; i++)
        mean += vals[i];
    mean /= m;
    den = 0.0;
    for (i = 0; i < m; i++) {
        double dd = vals[i] - mean;
        den += dd * dd;
    }
    var = den / m;
    sd = (var > 1e-12) ? sqrt(var) : 1e-6;

    /* head 1 -- derivative z-score with anomaly-aware HOLD baseline */
    dx = x - vals[m - 2];
    z_deriv = fabs(dx - d->mu_d) / (sqrt(d->var_d) + U_EPS);
    if (z_deriv < U_HOLD) {
        diff = dx - d->mu_d;
        d->mu_d += d->alpha * diff;
        d->var_d = (1.0 - d->alpha) * (d->var_d + d->alpha * diff * diff);
        if (d->var_d < 1e-6)
            d->var_d = 1e-6;
    }
    s_drv = z_deriv / U_TH_DRV;

    /* head 2 -- held EWMA control-chart, output CLIPPED at DR_CAP */
    control_sigma = sd * sqrt(d->lam / (2.0 - d->lam));
    s_ewmv = fabs(d->z - d->mu) / (control_sigma + U_EPS);
    d->z = d->lam * x + (1.0 - d->lam) * d->z;
    if (s_ewmv < U_TH_EWMV)
        d->mu += d->alpha_s * (x - d->mu);
    s_drift = s_ewmv / U_TH_EWMV;
    if (s_drift > U_DR_CAP)
        s_drift = U_DR_CAP;

    /* head 3 -- gated ACF-drop (arms once, only if the base is periodic) */
    s_per = 0.0;
    if (d->count == UNIFIED_BUF_LEN) {
        if (d->period == 0) {
            int best_lag = 0, lag, hi;
            double best_r = -2.0, rr;
            hi = UNIFIED_BUF_LEN / 2;
            if (hi < 3)
                hi = 3;
            for (lag = 2; lag <= hi; lag++) {
                rr = u_acf(vals, m, lag, mean, den);
                if (rr > best_r) {
                    best_r = rr;
                    best_lag = lag;
                }
            }
            d->period = (best_lag > 0) ? best_lag : 2;
            d->r_ref = best_r;
            d->armed = (best_r >= U_GATE) ? 1 : 0;
        } else if (d->armed) {
            double drop = d->r_ref - u_acf(vals, m, d->period, mean, den);
            if (drop > 0.0)
                s_per = drop / U_TH_PER;
        }
    }

    /* MAX fusion */
    score = s_drv;
    if (s_drift > score)
        score = s_drift;
    if (s_per > score)
        score = s_per;
    if (!warm)
        score = 0.0;
    d->last_score = score;
    return score;
}

int unified_state_bytes(void)
{
    /* float32 per-metric footprint model: 5 scalars + 17-deep buffer + int counters */
    return 5 * 4 + UNIFIED_BUF_LEN * 4 + 8;   /* = 96 */
}
