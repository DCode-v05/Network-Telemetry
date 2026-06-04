# Evaluate and compare lightweight time-series techniques for network telemetry using short observation windows (e.g., 10–50 samples)

---
## 1. Introduction

### 1.1 Context: The Shift Toward Edge Intelligence in Networking

#### The Big Picture: Making Routers Smarter

Imagine a **network router or switch** as a traffic cop at a busy intersection. Its main job is to direct data packets (small chunks of information) from one place to another — like how a traffic cop directs cars. Today's routers/switches are basically that: they forward packets and not much else.

But just like a traffic cop can *see* that traffic is getting heavier, or that a road is suddenly blocked, a router can *see* a lot about the network — how much data is flowing, how fast, whether errors are happening, etc. This data is called **telemetry** (think of it like a health monitor for the network). The problem? Routers currently do very little with this information on their own.

#### Technical Context

Network infrastructure is undergoing a fundamental transformation. Modern switches and routers are no longer passive packet-forwarding devices — they are becoming intelligent platforms capable of observing, analyzing, and reacting to network conditions in real time. Every network device already generates rich telemetry: interface utilization counters, packet rates, queue depths, error counts, jitter measurements, and protocol state transitions — often at sub-second granularity, producing thousands of data points per minute across hundreds of interfaces.

Today, this telemetry is largely consumed in one of two ways:

1. **Centralized collection and analysis** — Telemetry is exported (via SNMP, streaming telemetry, sFlow/NetFlow) to external collectors where server-class machines run analytics, machine learning models, or rule engines. This approach is powerful but introduces inherent delays (seconds to minutes), requires network bandwidth for export, depends on external infrastructure availability, and scales poorly as the number of monitored endpoints grows.

2. **Static threshold alerting** — Simple rules configured on the device (e.g., "alert if CPU > 90%", "alert if link utilization > 80%") trigger when a fixed boundary is crossed. This approach is fast and local, but fundamentally limited — it cannot detect gradual degradation, distinguish legitimate traffic peaks from anomalies, identify pattern changes, or adapt to varying baseline conditions.

Neither approach addresses the emerging need: **real-time, context-aware anomaly detection running directly on the network device itself** — what the industry calls "edge analytics" or "on-device intelligence."

### 1.2 The Opportunity: On-Device Intelligence

**This project proposes a third approach:** bring real-time, context-aware anomaly detection running directly on the network device itself — what the industry calls "edge analytics" or "on-device intelligence." Rather than shipping data to remote systems for analysis or relying on static thresholds, we can empower network switches to think locally with sufficient intelligence embedded in the control plane.

Network switches based on modern architectures (including ARM-based control planes) have sufficient compute headroom on their management processors to run lightweight analytics — provided those analytics are designed within strict resource constraints. The opportunity is to bring intelligence closer to the data source, enabling:

- **Sub-second detection latency** — Anomalies detected within a few samples rather than minutes
- **Zero export overhead** — Analysis happens where the data is generated
- **Resilience** — Detection continues even if connectivity to centralized systems is lost
- **Scalability** — Each device handles its own telemetry; no central bottleneck
- **Foundation for local AI** — Lightweight detectors can serve as feature extractors, pre-filters, or standalone modules within a future on-device AI framework

This project evaluates the **algorithmic building blocks** that make this vision practical.

### 1.3 Why Time-Series Analysis?

**What is time-series data?** A time series is simply a list of measurements taken at regular intervals over time. Network telemetry is inherently time-series data — ordered sequences of measurements such as:

- Interface utilization (packets per second)
- CPU usage (percentage utilization)
- Queue depths (packet counts)
- Error counters (drops, collisions)
- Protocol state transitions

Think of it like a heartrate monitor on a smartwatch, temperature readings from a weather station, or traffic volume on a router port measured every second. Time-series analysis is the natural mathematical framework for extracting patterns, trends, and anomalies from such data.

However, classical time-series methods (ARIMA model fitting, spectral analysis, Kalman filtering) were designed for datasets with hundreds or thousands of observations. Network on-device analytics must operate with **short observation windows** — typically 10 to 50 samples — because:

- Memory is constrained (no large circular buffers)
- Conditions change rapidly (a window from 5 minutes ago may be irrelevant)
- Detection must be fast (cannot wait to accumulate long histories)
- The device monitors many metrics simultaneously (memory multiplied across counters)

The central question of this project is: **Which time-series techniques remain effective and practical when constrained to very short observation windows and bounded computational resources?**

---

## 2. Problem Statement

### 2.1 The Problem

Network operators need to detect meaningful changes in network behavior — not just threshold crossings, but structural changes in traffic patterns, transient anomalies, periodicity disruptions, and subtle degradation trends. Current on-device mechanisms are limited to static thresholds that lack the ability to:

- Distinguish a legitimate traffic burst from an anomalous spike
- Detect that a previously periodic signal (e.g., keepalive traffic) has become irregular
- Identify a gradual rate shift that never crosses a fixed threshold
- Catch a brief transient anomaly (microburst, packet drop spike) that lasts only a few samples

Meanwhile, sophisticated time-series and ML-based techniques exist but are designed for environments with abundant compute, memory, and data — none of which are available on a network switch's control plane processor. This creates a critical gap: static threshold alerting is too simple, but sophisticated analytics are too resource-intensive.

### 2.2 Resource Constraints on Network Devices

The fundamental challenge is the extreme disparity between server-class analytics and on-device capabilities. There is no systematic, empirically-grounded comparison of lightweight time-series algorithms evaluated specifically under the constraints of network device deployment:

| Constraint | Typical Server Analytics | On-Device Requirement |
|---|---|---|
| Observation window | 1,000–100,000+ samples | **10–50 samples** |
| Compute per sample | Milliseconds acceptable | **< 100 microseconds** |
| Memory per metric | Megabytes available | **< 100 bytes** |
| Libraries available | Python, NumPy, SciPy, TensorFlow | **Basic C arithmetic only** |
| Processing model | Batch (reprocess entire window) | **Streaming (one sample at a time)** |
| Metrics monitored | Tens | **Hundreds to thousands simultaneously** |

### 2.3 What This Project Will Answer

This project will answer the following specific questions:

1. **Which algorithms work at all with 10–50 samples?** — Some techniques degrade gracefully; others fail entirely below a minimum data threshold. We need empirical evidence, not assumptions.

2. **What is the accuracy–window size tradeoff?** — For each algorithm, how does detection accuracy (precision, recall, F1) change as the window shrinks from 50 → 30 → 20 → 10 samples?

3. **What is the computational cost?** — For each algorithm, what is the per-sample CPU cost and memory footprint? Can it run thousands of times per second on an ARM processor?

4. **Which algorithm suits which anomaly type?** — Burst detection may need a different technique than periodicity detection. We need a mapping from *condition type* to *best algorithm*.

5. **Can algorithms be combined?** — Does a layered approach (e.g., EWMA baseline → CUSUM change-point → threshold alert) outperform any single algorithm?

6. **How do these techniques connect to on-device AI?** — Can lightweight detectors serve as feature extractors or pre-filters for future local ML models on switches?