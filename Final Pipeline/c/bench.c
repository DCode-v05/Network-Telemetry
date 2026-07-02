/* bench.c -- measured per-sample cost of the unified detector.
 *
 * Times a large number of unified_update() calls with QueryPerformanceCounter
 * (the same high-resolution timer used by the Phase 4 C bench) and reports the
 * REAL ns/sample (no theoretical estimate). Also prints the on-device state
 * footprint and checks both budget gates:  state_bytes < 100  AND  time < 100 us.
 *
 * Usage:  bench            (windows 24, 30, 50)
 * Exit code 0 = within budget, 1 = over budget.
 */
#include "unified.h"

#include <stdio.h>
#include <stdint.h>
#include <windows.h>

#define STREAM_LEN 2000
#define REPS       2000     /* 2000 * 2000 = 4,000,000 update() calls per window */

/* deterministic LCG -> telemetry-like random walk with occasional jumps */
static uint64_t rng_state = 0x9E3779B97F4A7C15ULL;
static double next_rand(void)
{
    rng_state = rng_state * 6364136223846793005ULL + 1442695040888963407ULL;
    return (double)(rng_state >> 11) / (double)(1ULL << 53);
}

static void make_stream(double *out, int n)
{
    double level = 50.0;
    int i;
    for (i = 0; i < n; i++) {
        if (next_rand() < 0.02)
            level += (next_rand() - 0.5) * 40.0;   /* occasional jump */
        out[i] = level + (next_rand() - 0.5) * 2.0; /* + noise */
    }
}

static double bench_window(int window, const double *stream)
{
    UnifiedDetector d;
    LARGE_INTEGER freq, t0, t1;
    volatile double sink = 0.0;
    int r, i;

    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&t0);
    for (r = 0; r < REPS; r++) {
        unified_init(&d, window);
        for (i = 0; i < STREAM_LEN; i++)
            sink += unified_update(&d, stream[i]);
    }
    QueryPerformanceCounter(&t1);

    if (sink == 1234567.0)          /* liveness guard: stop the loop being elided */
        printf(" ");

    double total_s = (double)(t1.QuadPart - t0.QuadPart) / (double)freq.QuadPart;
    double ns_per_sample = total_s * 1e9 / ((double)REPS * STREAM_LEN);
    return ns_per_sample;
}

int main(void)
{
    double stream[STREAM_LEN];
    int windows[] = {24, 30, 50};
    int nw = 3, w, all_ok = 1;

    make_stream(stream, STREAM_LEN);

    printf("bench: unified detector  (%d x %d = %d updates per window)\n",
           REPS, STREAM_LEN, REPS * STREAM_LEN);
    printf("  sizeof(UnifiedDetector) = %d bytes (double compute struct)\n",
           (int)sizeof(UnifiedDetector));
    printf("  state_bytes()           = %d bytes (float32 on-device model)\n\n",
           unified_state_bytes());
    printf("  %-8s %14s %14s %10s\n", "window", "ns/sample", "us/sample", "budget");
    printf("  %-8s %14s %14s %10s\n", "------", "---------", "---------", "------");

    for (w = 0; w < nw; w++) {
        double ns = bench_window(windows[w], stream);
        double us = ns / 1000.0;
        int bytes_ok = unified_state_bytes() < 100;
        int time_ok = us < 100.0;
        int ok = bytes_ok && time_ok;
        if (!ok)
            all_ok = 0;
        printf("  %-8d %14.2f %14.5f %10s\n",
               windows[w], ns, us, ok ? "OK" : "OVER");
    }

    printf("\n  budget gate: state_bytes < 100 AND us/sample < 100  ->  %s\n",
           all_ok ? "PASS" : "FAIL");
    return all_ok ? 0 : 1;
}
