"""
TwoLayerEnsemble — top-level Phase 3 detector.

Combines:
- A spike layer (e.g. AND-vote of GatedMAD + GatedZScore) for short anomalies.
- A sustained-change layer (e.g. OR-vote of GatedEWMA + GatedCUSUM) for shifts.

Default fusion: alarm if either layer fires. Per-layer confirmation gates and
voting suppress most singleton FPs upstream, so the OR fusion at this level
preserves coverage across all four anomaly types without re-introducing noise.

`alarm_value` encodes attribution for the dashboard:
    1.0 — only the spike layer fired (or both)
    2.0 — only the sustained layer fired
    0.0 — neither fired
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _phase2_bridge import DetectorBase, DetectionResult


class TwoLayerEnsemble(DetectorBase):
    """
    Spike-layer + sustained-change-layer fusion.

    Parameters
    ----------
    spike_layer     : DetectorBase    — typically a VotingLayer over gated children.
    sustained_layer : DetectorBase    — typically a VotingLayer over gated children.
    use_routing     : bool (default False)
        Reserved for an experimental per-anomaly-type routing mode that uses
        ground-truth labels at test time. KEEP OFF for honest evaluation —
        the flag exists only for ablation studies.
    name_suffix     : str (default "")
        Optional tag appended to `name`, useful when several ensemble variants
        appear in the same benchmark sweep.
    """

    def __init__(
        self,
        spike_layer: DetectorBase,
        sustained_layer: DetectorBase,
        use_routing: bool = False,
        name_suffix: str = "",
    ):
        self._spike       = spike_layer
        self._sustained   = sustained_layer
        self._use_routing = bool(use_routing)
        self._name_suffix = name_suffix

    @property
    def name(self) -> str:
        suffix = f"[{self._name_suffix}]" if self._name_suffix else ""
        return f"TwoLayerEnsemble{suffix}"

    def update(self, value: float) -> DetectionResult:
        spike_r     = self._spike.update(value)
        sustained_r = self._sustained.update(value)

        is_anomaly = spike_r.is_anomaly or sustained_r.is_anomaly
        score      = max(spike_r.score, sustained_r.score)

        if spike_r.is_anomaly:
            alarm_value = 1.0
        elif sustained_r.is_anomaly:
            alarm_value = 2.0
        else:
            alarm_value = 0.0

        return DetectionResult(
            is_anomaly  = is_anomaly,
            score       = score,
            alarm_value = alarm_value,
        )

    def reset(self) -> None:
        self._spike.reset()
        self._sustained.reset()
