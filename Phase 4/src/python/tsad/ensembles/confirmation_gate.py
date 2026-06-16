"""Confirmation gate: require N consecutive over-threshold child alarms before firing.

Wraps any registered detector and suppresses isolated (single-sample) over-threshold blips
-- the dominant false-positive mode on tail noise -- while passing sustained anomalies
(drift, periodicity) almost untouched. It is the precision lever for sustained-type
detectors. The emitted score is the child's score once a run of `confirm` consecutive
over-threshold samples is seen, and 0.0 otherwise, so threshold sweeps behave naturally.

(Point anomalies that last < `confirm` samples are intentionally NOT gated -- use the
ungated `deriv`/`robust_z` for spikes/transients.)
"""

from __future__ import annotations

from tsad.core.base import Detector


class ConfirmationGate(Detector):
    name = "confirmation_gate"

    def __init__(self, window=30, threshold=0.5, child="cusum", confirm=2, **params):
        self.child_name = child
        self.confirm = int(confirm)
        super().__init__(window=window, threshold=threshold, **params)

    def reset(self):
        super().reset()
        import tsad.registry as registry
        self.child = registry.make(self.child_name, window=self.window)
        self.threshold = self.child.threshold
        self.run = 0

    def update(self, x):
        self.n += 1
        s = self.child.update(x)
        if s >= self.child.threshold:
            self.run += 1
        else:
            self.run = 0
        score = s if self.run >= self.confirm else 0.0
        if not self.warm():
            score = 0.0
        self.last_score = score
        return score

    def state_bytes(self):
        return self.child.state_bytes() + 8
