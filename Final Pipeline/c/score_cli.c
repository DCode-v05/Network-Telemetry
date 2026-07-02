/* score_cli.c -- stream telemetry values through the C unified detector.
 *
 * Reads whitespace-separated doubles from stdin (the already-preprocessed feed)
 * and prints, one line per sample:  score  s_drv  s_drift  s_per
 *
 * Used by the dashboard engine server (server.py) so the Live Pipeline can run
 * "in C": the server pipes the stream in and reads the scores back.
 *
 * Usage:  score_cli [window]     (window default 24)
 */
#include "unified.h"

#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    int window = (argc > 1) ? atoi(argv[1]) : 24;
    UnifiedDetector d;
    unified_init(&d, window);

    double x;
    while (scanf("%lf", &x) == 1) {
        double s = unified_update(&d, x);
        printf("%.10g %.10g %.10g %.10g\n", s, d.s_drv, d.s_drift, d.s_per);
    }
    return 0;
}
