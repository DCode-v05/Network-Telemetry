/* bench.c -- per-detector throughput microbenchmark (Windows QPC).
 *
 * For each TsadKind and window in {10,20,30,50} it builds a pseudo-random
 * stream of ~2000 doubles, runs tsad_update over it repeatedly (enough reps for
 * a measurable total time), times it with QueryPerformanceCounter, and computes
 * c_ns_per_sample. It prints a CSV to stdout AND writes results/c_cost.csv.
 *
 * CSV header:
 *   detector,window,c_ns_per_sample,c_us_per_sample,sizeof_struct_bytes,c_state_bytes
 */
#include "tsad.h"
#include <stdio.h>
#include <stdlib.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#define STREAM_LEN 2000
#define REPS       2000

/* Output path for the CSV copy. */
#define OUT_CSV \
  "d:\\Deni\\Mr.Tech\\Experience\\Internships\\HP CPP\\Code\\Phase 4\\results\\c_cost.csv"

/* Small deterministic LCG so the stream is reproducible across runs/platforms. */
static unsigned long long g_rng = 0x9E3779B97F4A7C15ULL;
static double next_rand(void) {
    g_rng = g_rng * 6364136223846793005ULL + 1442695040888963407ULL;
    /* take top 32 bits -> [0,1) */
    unsigned int top = (unsigned int)(g_rng >> 32);
    return (double)top / 4294967296.0;
}

int main(void) {
    static double stream[STREAM_LEN];
    static const int windows[] = {10, 20, 30, 50};
    const int n_windows = (int)(sizeof(windows) / sizeof(windows[0]));

    LARGE_INTEGER freq, t0, t1;
    int ki, wi, rep, i;
    FILE *fp;
    const char *header =
        "detector,window,c_ns_per_sample,c_us_per_sample,"
        "sizeof_struct_bytes,c_state_bytes\n";

    QueryPerformanceFrequency(&freq);

    /* Build a pseudo-random stream once (mildly autocorrelated random walk with
     * occasional spikes), reused across detectors/windows so the work per call
     * is representative. */
    {
        double v = 0.0;
        for (i = 0; i < STREAM_LEN; ++i) {
            double step = (next_rand() - 0.5) * 2.0;
            v += step * 0.3;
            if (next_rand() > 0.98) v += (next_rand() - 0.5) * 20.0; /* spike */
            stream[i] = v + (next_rand() - 0.5);
        }
    }

    fp = fopen(OUT_CSV, "w");
    /* Print header to stdout (and file if it opened). */
    fputs(header, stdout);
    if (fp) fputs(header, fp);

    for (ki = 0; ki < TSAD_KIND_COUNT; ++ki) {
        for (wi = 0; wi < n_windows; ++wi) {
            int window = windows[wi];
            TsadDetector d;
            volatile double sink = 0.0; /* prevent the loop being optimized away */
            double total_s, ns_per_sample, us_per_sample;
            long long total_samples;
            int sizeof_struct, state_bytes;

            QueryPerformanceCounter(&t0);
            for (rep = 0; rep < REPS; ++rep) {
                tsad_init(&d, (TsadKind)ki, window);
                for (i = 0; i < STREAM_LEN; ++i) {
                    sink += tsad_update(&d, stream[i]);
                }
            }
            QueryPerformanceCounter(&t1);

            total_s = (double)(t1.QuadPart - t0.QuadPart) / (double)freq.QuadPart;
            total_samples = (long long)REPS * (long long)STREAM_LEN;
            ns_per_sample = total_s * 1e9 / (double)total_samples;
            us_per_sample = ns_per_sample / 1000.0;

            sizeof_struct = (int)sizeof(TsadDetector);
            state_bytes = tsad_state_bytes((TsadKind)ki, window);

            /* keep sink alive */
            if (sink == 1234567.0) fprintf(stderr, "x");

            printf("%s,%d,%.4f,%.6f,%d,%d\n",
                   tsad_slug((TsadKind)ki), window,
                   ns_per_sample, us_per_sample, sizeof_struct, state_bytes);
            if (fp) {
                fprintf(fp, "%s,%d,%.4f,%.6f,%d,%d\n",
                        tsad_slug((TsadKind)ki), window,
                        ns_per_sample, us_per_sample, sizeof_struct, state_bytes);
            }
        }
    }

    if (fp) fclose(fp);
    return 0;
}
