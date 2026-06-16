/* parity.c -- numerical-parity harness for the C twin.
 *
 * Usage:  parity <slug> <window>
 * Reads doubles from stdin (whitespace/newline separated) until EOF. For EACH
 * value it prints the tsad_update score with printf("%.10g\n", score).
 * One score per input value. No extra output on stdout.
 */
#include "tsad.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    TsadDetector d;
    int kind, window;
    double x;

    if (argc < 3) {
        fprintf(stderr, "usage: %s <slug> <window>\n", argv[0]);
        return 2;
    }

    kind = tsad_kind_from_slug(argv[1]);
    if (kind < 0) {
        fprintf(stderr, "unknown slug: %s\n", argv[1]);
        return 2;
    }

    window = atoi(argv[2]);
    if (window < 1) {
        fprintf(stderr, "bad window: %s\n", argv[2]);
        return 2;
    }

    tsad_init(&d, (TsadKind)kind, window);

    while (scanf("%lf", &x) == 1) {
        double score = tsad_update(&d, x);
        printf("%.10g\n", score);
    }

    return 0;
}
