/* tsad.c -- C99 implementation of the nine Phase 4 streaming detectors.
 *
 * Ported line-for-line from the Python reference (tsad/core and
 * tsad/detectors). All arithmetic is in double precision to match the
 * float64 Python reference to < 1e-4.
 *
 * Key invariants mirrored from Python:
 *   - base warm-up: warmup = max(3, window/3); update returns 0.0 while
 *     n <= warmup (i.e. while NOT (n > warmup)).
 *   - ring buffer: push overwrites oldest when full; values() are chronological
 *     oldest -> newest.
 *   - median_sorted averages the two middles for even length.
 *   - mad = median of the sorted |v - med| deviations (raw, not scaled).
 *   - predict-then-update ordering and post-alarm resets reproduced exactly.
 */
#include "tsad.h"
#include <math.h>
#include <string.h>

/* ----- shared constants (mirror the Python module-level constants) -------- */
#define EWMA_EPS        1e-9
#define ROBUST_EPS      1e-9
#define HAMPEL_EPS      1e-9
#define CUSUM_EPS       1e-9
#define CUSUM_SLACK_K   0.5
#define CUSUM_SD_FLOOR  1e-6
#define EWMV_EPS        1e-9
#define EWMV_SIGMA_FLOOR 1e-6
#define DERIV_EPS       1e-9
#define HEAVY_EPS       1e-9
#define ACF_EPS         1e-9
#define MAD_TO_SIGMA    1.4826

/* ----- slug table (order matches TsadKind) -------------------------------- */
static const char *const SLUGS[TSAD_KIND_COUNT] = {
    "ewma_z",
    "robust_z",
    "hampel",
    "cusum",
    "page_hinkley",
    "ewmv_adaptive",
    "deriv",
    "acf_periodicity",
    "heavy_baseline"
};

const char *tsad_slug(TsadKind kind) {
    if (kind < 0 || kind >= TSAD_KIND_COUNT) return "";
    return SLUGS[kind];
}

int tsad_kind_from_slug(const char *slug) {
    int i;
    if (!slug) return -1;
    for (i = 0; i < TSAD_KIND_COUNT; ++i) {
        if (strcmp(slug, SLUGS[i]) == 0) return i;
    }
    return -1;
}

/* ----- ring-buffer helpers (mirror tsad/core/ring_buffer.py) -------------- */

/* push: append a value, overwriting the oldest once full. O(1). */
static void ring_push(TsadDetector *d, double x) {
    d->buf[d->head] = x;
    d->head = (d->head + 1) % d->window;
    if (d->count < d->window) d->count += 1;
}

/* Copy valid values in chronological (oldest -> newest) order into out[].
 * Returns the count. Mirrors RingBuffer.values(). */
static int ring_values(const TsadDetector *d, double *out) {
    int i, idx;
    if (d->count < d->window) {
        for (i = 0; i < d->count; ++i) out[i] = d->buf[i];
        return d->count;
    }
    /* full: buf[head:] + buf[:head] */
    idx = 0;
    for (i = d->head; i < d->window; ++i) out[idx++] = d->buf[i];
    for (i = 0; i < d->head; ++i) out[idx++] = d->buf[i];
    return d->count;
}

/* ascending insertion sort, in place. */
static void insertion_sort(double *a, int n) {
    int i, j;
    for (i = 1; i < n; ++i) {
        double key = a[i];
        j = i - 1;
        while (j >= 0 && a[j] > key) {
            a[j + 1] = a[j];
            --j;
        }
        a[j + 1] = key;
    }
}

/* ----- stats helpers (mirror tsad/core/stats.py) -------------------------- */

/* median of an already-sorted array; averages the two middles for even len. */
static double median_sorted(const double *sv, int m) {
    int mid;
    if (m == 0) return 0.0;
    mid = m / 2;
    if (m % 2) return sv[mid];
    return 0.5 * (sv[mid - 1] + sv[mid]);
}

/* median absolute deviation about med (raw, NOT scaled by 1.4826).
 * vals are the chronological values; scratch must hold >= n doubles. */
static double mad_about(const double *vals, int n, double med, double *scratch) {
    int i;
    if (n == 0) return 0.0;
    for (i = 0; i < n; ++i) {
        double v = vals[i] - med;
        scratch[i] = v < 0.0 ? -v : v;
    }
    insertion_sort(scratch, n);
    return median_sorted(scratch, n);
}

/* lag-`lag` autocorrelation of vals[0..N-1] (mean-centred, biased denom).
 * Returns 0.0 when there are too few samples. Mirrors acf_periodicity.acf. */
static double acf(const double *vals, int N, int lag) {
    int i;
    double mean = 0.0, num = 0.0, den = 0.0;
    if (N <= lag + 2) return 0.0;
    for (i = 0; i < N; ++i) mean += vals[i];
    mean /= (double)N;
    for (i = lag; i < N; ++i) num += (vals[i] - mean) * (vals[i - lag] - mean);
    for (i = 0; i < N; ++i) {
        double dv = vals[i] - mean;
        den += dv * dv;
    }
    den += ACF_EPS;
    return num / den;
}

/* warm(): True once n > warmup (allowed to alert). */
static int tsad_warm(const TsadDetector *d) {
    return d->n > d->warmup;
}

/* ----- lifecycle ---------------------------------------------------------- */

void tsad_reset(TsadDetector *d) {
    /* base.reset(): n = 0, last_score = 0.0 */
    d->n = 0;

    /* clear all union scalars / buffer */
    d->mu = 0.0; d->var = 0.0; d->sd = 0.0;
    d->g_pos = 0.0; d->g_neg = 0.0;
    d->xbar = 0.0; d->m_up = 0.0; d->min_up = 0.0; d->m_dn = 0.0; d->min_dn = 0.0;
    d->z = 0.0; d->mu_s = 0.0; d->sigma = 0.0;
    d->x_prev = 0.0; d->mu_d = 0.0; d->var_d = 0.0; d->r_ref = 0.0;
    d->period = 0;
    memset(d->buf, 0, sizeof(d->buf));
    d->head = 0;
    d->count = 0;

    switch (d->kind) {
    case TSAD_EWMA_Z:
        d->alpha = 2.0 / (d->window + 1.0);
        d->mu = 0.0;
        d->var = 1.0;
        break;
    case TSAD_ROBUST_Z:
    case TSAD_HAMPEL:
        /* state lives entirely in the ring buffer */
        break;
    case TSAD_CUSUM:
        d->alpha = 2.0 / (d->window + 1.0);
        d->mu = 0.0;
        d->sd = 1.0;
        d->g_pos = 0.0;
        d->g_neg = 0.0;
        break;
    case TSAD_PAGE_HINKLEY:
        /* _alpha = 2/(window+1), _delta = 0.005 (delta stored in alpha2 below) */
        d->alpha = 2.0 / (d->window + 1.0);
        d->xbar = 0.0;
        d->sd = 1.0;
        d->m_up = 0.0;
        d->min_up = 0.0;
        d->m_dn = 0.0;
        d->min_dn = 0.0;
        break;
    case TSAD_EWMV_ADAPTIVE:
        /* lam = 2/(window+1); alpha_s = lam/4 */
        d->alpha = 2.0 / (d->window + 1.0);   /* lam */
        d->z = 0.0;
        d->mu = 0.0;
        d->sigma = 1.0;
        break;
    case TSAD_DERIV:
        d->alpha = 2.0 / (d->window + 1.0);
        d->x_prev = 0.0;
        d->mu_d = 0.0;
        d->var_d = 1.0;
        break;
    case TSAD_ACF:
        d->period = 0;
        d->r_ref = 0.0;
        break;
    case TSAD_HEAVY:
        /* state lives entirely in the ring buffer */
        break;
    default:
        break;
    }
}

void tsad_init(TsadDetector *d, TsadKind kind, int window) {
    if (window < 1) window = 1;
    if (window > TSAD_MAXW) window = TSAD_MAXW;
    d->kind = kind;
    d->window = window;
    /* warmup = max(3, window // 3) */
    {
        int w3 = window / 3;
        d->warmup = (w3 > 3) ? w3 : 3;
    }

    /* default thresholds per detector (from each subclass __init__). Not used
     * by tsad_update (the score is threshold-independent except for the
     * post-alarm resets in cusum / page_hinkley), but kept faithful. */
    switch (kind) {
    case TSAD_EWMA_Z:       d->threshold = 3.0; break;
    case TSAD_ROBUST_Z:     d->threshold = 3.5; break;
    case TSAD_HAMPEL:       d->threshold = 3.0; break;
    case TSAD_CUSUM:        d->threshold = 5.0; break;
    case TSAD_PAGE_HINKLEY: d->threshold = 5.0; break;
    case TSAD_EWMV_ADAPTIVE:d->threshold = 3.0; break;
    case TSAD_DERIV:        d->threshold = 4.0; break;
    case TSAD_ACF:          d->threshold = 0.3; break;
    case TSAD_HEAVY:        d->threshold = 3.0; break;
    default:                d->threshold = 3.0; break;
    }

    tsad_reset(d);
}

/* ----- per-detector update implementations -------------------------------- */

static double upd_ewma_z(TsadDetector *d, double x) {
    double sd, z, diff, score;
    d->n += 1;
    if (d->n == 1) {
        d->mu = x;
        d->var = 1.0;
        return 0.0;
    }
    sd = sqrt(d->var);
    z = fabs(x - d->mu) / (sd + EWMA_EPS);

    diff = x - d->mu;
    d->mu += d->alpha * diff;
    d->var = (1.0 - d->alpha) * (d->var + d->alpha * diff * diff);

    score = z;
    if (!tsad_warm(d)) score = 0.0;
    return score;
}

static double upd_robust_z(TsadDetector *d, double x) {
    double score = 0.0;
    d->n += 1;
    if (d->count >= 3) {
        double vals[TSAD_MAXW], sv[TSAD_MAXW], scratch[TSAD_MAXW];
        double med, m, sd;
        int n = ring_values(d, vals);
        memcpy(sv, vals, (size_t)n * sizeof(double));
        insertion_sort(sv, n);
        med = median_sorted(sv, n);
        m = mad_about(vals, n, med, scratch);
        sd = MAD_TO_SIGMA * m;
        score = fabs(x - med) / (sd + ROBUST_EPS);
    }
    /* predict-then-update */
    ring_push(d, x);
    if (!tsad_warm(d)) score = 0.0;
    return score;
}

static double upd_hampel(TsadDetector *d, double x) {
    double score = 0.0;
    d->n += 1;
    /* current sample is part of the window (key difference vs robust_z) */
    ring_push(d, x);
    if (d->count >= 3) {
        double vals[TSAD_MAXW], sv[TSAD_MAXW], scratch[TSAD_MAXW];
        double med, m, sd;
        int n = ring_values(d, vals);
        memcpy(sv, vals, (size_t)n * sizeof(double));
        insertion_sort(sv, n);
        med = median_sorted(sv, n);
        m = mad_about(vals, n, med, scratch);
        sd = MAD_TO_SIGMA * m;
        score = fabs(x - med) / (sd + HAMPEL_EPS);
    }
    if (!tsad_warm(d)) score = 0.0;
    return score;
}

static double upd_cusum(TsadDetector *d, double x) {
    double alpha, k, r, score, diff;
    d->n += 1;
    if (d->n == 1) {
        d->mu = x;
        d->sd = 1.0;
        return 0.0;
    }
    alpha = d->alpha;
    k = CUSUM_SLACK_K;

    r = (x - d->mu) / (d->sd + CUSUM_EPS);
    d->g_pos = d->g_pos + r - k; if (d->g_pos < 0.0) d->g_pos = 0.0;
    d->g_neg = d->g_neg - r - k; if (d->g_neg < 0.0) d->g_neg = 0.0;
    score = (d->g_pos > d->g_neg) ? d->g_pos : d->g_neg;

    diff = x - d->mu;
    d->mu += alpha * diff;
    d->sd = sqrt((1.0 - alpha) * (d->sd * d->sd + alpha * diff * diff));
    if (d->sd < CUSUM_SD_FLOOR) d->sd = CUSUM_SD_FLOOR;

    if (score >= d->threshold) {
        d->g_pos = 0.0;
        d->g_neg = 0.0;
    }

    if (!tsad_warm(d)) score = 0.0;
    return score;
}

static double upd_page_hinkley(TsadDetector *d, double x) {
    double alpha = d->alpha;
    double delta = 0.005;
    double dd, e, ph_up, ph_dn, score;
    d->n += 1;

    d->xbar += (x - d->xbar) / (double)d->n;
    dd = x - d->xbar;
    d->sd = sqrt((1.0 - alpha) * (d->sd * d->sd + alpha * dd * dd));
    if (d->sd < 1e-6) d->sd = 1e-6;

    e = (x - d->xbar) / (d->sd + 1e-9);

    d->m_up += (e - delta);
    if (d->m_up < d->min_up) d->min_up = d->m_up;
    ph_up = d->m_up - d->min_up;

    d->m_dn += (-e - delta);
    if (d->m_dn < d->min_dn) d->min_dn = d->m_dn;
    ph_dn = d->m_dn - d->min_dn;

    score = (ph_up > ph_dn) ? ph_up : ph_dn;

    if (score >= d->threshold) {
        d->m_up = 0.0;
        d->min_up = 0.0;
        d->m_dn = 0.0;
        d->min_dn = 0.0;
    }

    if (!tsad_warm(d)) score = 0.0;
    return score;
}

static double upd_ewmv_adaptive(TsadDetector *d, double x) {
    double lam = d->alpha;          /* lam = 2/(window+1) */
    double alpha_s = lam / 4.0;
    double control_sigma, score, dd;
    d->n += 1;
    if (d->n == 1) {
        d->z = x;
        d->mu = x;
        d->sigma = 1.0;
        return 0.0;
    }
    control_sigma = d->sigma * sqrt(lam / (2.0 - lam));
    score = fabs(d->z - d->mu) / (control_sigma + EWMV_EPS);

    d->z = lam * x + (1.0 - lam) * d->z;
    dd = x - d->mu;
    d->mu += alpha_s * dd;
    d->sigma = sqrt((1.0 - alpha_s) * (d->sigma * d->sigma + alpha_s * dd * dd));
    if (d->sigma < EWMV_SIGMA_FLOOR) d->sigma = EWMV_SIGMA_FLOOR;

    if (!tsad_warm(d)) score = 0.0;
    return score;
}

static double upd_deriv(TsadDetector *d, double x) {
    double alpha = d->alpha;       /* 2/(window+1) */
    double dd, sd, score, diff;
    d->n += 1;
    if (d->n == 1) {
        d->x_prev = x;
        d->mu_d = 0.0;
        d->var_d = 1.0;
        return 0.0;
    }
    dd = x - d->x_prev;
    sd = sqrt(d->var_d);
    score = fabs(dd - d->mu_d) / (sd + DERIV_EPS);

    diff = dd - d->mu_d;
    d->mu_d += alpha * diff;
    d->var_d = (1.0 - alpha) * (d->var_d + alpha * diff * diff);

    d->x_prev = x;

    if (!tsad_warm(d)) score = 0.0;
    return score;
}

static double upd_acf(TsadDetector *d, double x) {
    double vals[TSAD_MAXW];
    int n;
    double r_now, score;
    d->n += 1;
    ring_push(d, x);

    /* still filling the observation window */
    if (d->count < d->window) return 0.0;

    n = ring_values(d, vals);

    /* establish the dominant period exactly once */
    if (d->period == 0) {
        int best_lag = 0, lag;
        double best_r = -2.0;
        int hi = d->window / 2;
        if (hi < 3) hi = 3;                 /* max(3, window//2) */
        for (lag = 2; lag <= hi; ++lag) {
            double r = acf(vals, n, lag);
            if (r > best_r) { best_r = r; best_lag = lag; }
        }
        if (best_r < 0.2) {
            int p = d->window / 4;          /* max(2, window//4) */
            d->period = (p > 2) ? p : 2;
            d->r_ref = 0.05;
        } else {
            d->period = best_lag;
            d->r_ref = best_r;
        }
        return 0.0;
    }

    r_now = acf(vals, n, d->period);
    score = d->r_ref - r_now;
    if (score < 0.0) score = 0.0;
    if (!tsad_warm(d)) score = 0.0;
    return score;
}

static double upd_heavy(TsadDetector *d, double x) {
    double vals[TSAD_MAXW];
    int N = ring_values(d, vals);
    double score = 0.0;
    d->n += 1;

    if (N >= 4) {
        double st, stt, sy, sty, denom, b, a, pred, mean, var, std;
        double sv[TSAD_MAXW], scratch[TSAD_MAXW];
        double med, m, rob, scale;
        int t;

        st = (double)N * (double)(N - 1) / 2.0;
        stt = 0.0;
        for (t = 0; t < N; ++t) stt += (double)t * (double)t;
        sy = 0.0;
        for (t = 0; t < N; ++t) sy += vals[t];
        sty = 0.0;
        for (t = 0; t < N; ++t) sty += (double)t * vals[t];
        denom = ((double)N * stt - st * st) + HEAVY_EPS;
        b = ((double)N * sty - st * sy) / denom;
        a = (sy - b * st) / (double)N;
        pred = a + b * (double)N;

        mean = sy / (double)N;
        var = 0.0;
        for (t = 0; t < N; ++t) {
            double dv = vals[t] - mean;
            var += dv * dv;
        }
        var /= (double)N;
        std = sqrt(var);

        memcpy(sv, vals, (size_t)N * sizeof(double));
        insertion_sort(sv, N);
        med = median_sorted(sv, N);
        m = mad_about(vals, N, med, scratch);
        rob = MAD_TO_SIGMA * m;

        scale = (std > rob) ? std : rob;
        score = fabs(x - pred) / (scale + HEAVY_EPS);
    }

    ring_push(d, x);

    if (!tsad_warm(d)) score = 0.0;
    return score;
}

double tsad_update(TsadDetector *d, double x) {
    switch (d->kind) {
    case TSAD_EWMA_Z:        return upd_ewma_z(d, x);
    case TSAD_ROBUST_Z:      return upd_robust_z(d, x);
    case TSAD_HAMPEL:        return upd_hampel(d, x);
    case TSAD_CUSUM:         return upd_cusum(d, x);
    case TSAD_PAGE_HINKLEY:  return upd_page_hinkley(d, x);
    case TSAD_EWMV_ADAPTIVE: return upd_ewmv_adaptive(d, x);
    case TSAD_DERIV:         return upd_deriv(d, x);
    case TSAD_ACF:           return upd_acf(d, x);
    case TSAD_HEAVY:         return upd_heavy(d, x);
    default:                 return 0.0;
    }
}

/* ----- float32 deployment footprint (matches Python state_bytes) ---------- */
int tsad_state_bytes(TsadKind kind, int window) {
    int floats = 0, buf = 0;
    switch (kind) {
    case TSAD_EWMA_Z:        floats = 2; buf = 0;      break; /* mu, var */
    case TSAD_ROBUST_Z:      floats = 0; buf = window; break;
    case TSAD_HAMPEL:        floats = 0; buf = window; break;
    case TSAD_CUSUM:         floats = 4; buf = 0;      break; /* mu,sd,g_pos,g_neg */
    case TSAD_PAGE_HINKLEY:  floats = 6; buf = 0;      break; /* xbar,sd,m_up,min_up,m_dn,min_dn */
    case TSAD_EWMV_ADAPTIVE: floats = 3; buf = 0;      break; /* z,mu,sigma */
    case TSAD_DERIV:         floats = 3; buf = 0;      break; /* x_prev,mu_d,var_d */
    case TSAD_ACF:           floats = 2; buf = window; break; /* period,r_ref + window */
    case TSAD_HEAVY:         floats = 0; buf = window; break;
    default:                 floats = 0; buf = 0;      break;
    }
    return floats * 4 + buf * 4 + 8; /* +8: n + flags */
}
