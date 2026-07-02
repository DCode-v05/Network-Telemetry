/* parity_check.c -- assert the C twin matches the Python reference.
 *
 * Reads build/parity_data.txt (written by parity_gen.py): one "value py_score"
 * pair per line. Streams each value through the C unified_update and compares
 * the C score against the Python score. Prints the max absolute difference and
 * PASS/FAIL at tolerance 1e-4.
 *
 * Usage:  parity_check [data_file] [window]
 *   data_file  default: build/parity_data.txt
 *   window     default: 24  (must match parity_gen.py)
 *
 * Exit code 0 = PASS, 1 = FAIL / error.
 */
#include "unified.h"

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define TOL 1e-4

int main(int argc, char **argv)
{
    const char *path = (argc > 1) ? argv[1] : "build/parity_data.txt";
    int window = (argc > 2) ? atoi(argv[2]) : 24;

    FILE *f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "parity_check: cannot open %s\n", path);
        fprintf(stderr, "  run: python parity_gen.py   (from Final Pipeline/c)\n");
        return 1;
    }

    UnifiedDetector d;
    unified_init(&d, window);

    double value, py_score;
    double max_diff = 0.0;
    long n = 0, worst_i = -1;
    double worst_c = 0.0, worst_py = 0.0;

    while (fscanf(f, "%lf %lf", &value, &py_score) == 2) {
        double c_score = unified_update(&d, value);
        double diff = fabs(c_score - py_score);
        if (diff > max_diff) {
            max_diff = diff;
            worst_i = n;
            worst_c = c_score;
            worst_py = py_score;
        }
        n++;
    }
    fclose(f);

    if (n == 0) {
        fprintf(stderr, "parity_check: no samples read from %s\n", path);
        return 1;
    }

    printf("parity_check: detector=unified  window=%d  samples=%ld\n", window, n);
    printf("  state_bytes         = %d  (budget < 100)\n", unified_state_bytes());
    printf("  max |C - Python|    = %.3e  (tolerance %.0e)\n", max_diff, TOL);
    if (worst_i >= 0)
        printf("  worst @ sample %ld  : C=%.10g  Python=%.10g\n", worst_i, worst_c, worst_py);

    if (max_diff <= TOL) {
        printf("PARITY: PASS\n");
        return 0;
    }
    printf("PARITY: FAIL\n");
    return 1;
}
