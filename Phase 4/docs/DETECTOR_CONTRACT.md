# Detector contract (read before implementing any detector)

Every detector — Python reference **and** its on-device C twin — obeys this contract.

## Interface
```python
from tsad.core.base import Detector

class MyDet(Detector):
    name = "my_det"                       # matches the registry slug

    def reset(self):
        super().reset()                   # sets self.n = 0, self.last_score = 0.0
        # allocate fixed state here (scalars / one RingBuffer)

    def update(self, x: float) -> float:
        self.n += 1
        # ... pure scalar arithmetic only (no numpy) ...
        score = ...                       # >= 0.0, higher == more anomalous
        if not self.warm():               # self.n <= self.warmup
            score = 0.0                   # not enough data to judge yet
        self.last_score = score
        return score
```

## Hard rules
1. **Pure scalar arithmetic** in `update` — no numpy, no full-history passes. `math.sqrt`,
   `abs`, comparisons, the shared `tsad.core.stats` helpers and one `RingBuffer` are OK.
2. **Bounded state**, allocated once in `reset`. `update` is O(1) or O(window).
3. `update(x)` returns a **non-negative score**; **higher = more anomalous**.
4. The binary decision is `score >= self.threshold`. Pick a sensible default threshold.
5. During **warm-up** (`not self.warm()`) return `0.0`.
6. Implement `state_floats()` and (if you keep a buffer) `state_buffer_len()` so the
   footprint estimate matches the C struct and the < 100 byte budget can be checked.

## Normalization convention (so ensembles can combine detectors)
A detector's `self.threshold` is its decision boundary. Ensembles combine detectors by
the **normalized score** `score / threshold` (>= 1.0 means that detector fires). Keep
scores on a stable scale (e.g. z-score-like or cumulative-statistic-like) so this holds.

## Predict-then-update
To avoid an anomaly masking itself, compute the score from the state BEFORE folding `x`
into the baseline (where the algorithm allows), then update the baseline with `x`.

## Self-test (run before declaring done)
From `Phase 4/src/python`:
```
python -c "from tsad.registry import make; d=make('my_det', window=20); \
print([round(d.update(v),2) for v in [50,50.1,49.9,50,80,50,50.1]])"
```
A clear spike (the `80`) must produce a visibly larger score than the calm samples.
