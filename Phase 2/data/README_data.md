# Data Directory

Place your CESNET ip_addresses_sample CSVs here.

## Expected structure

```
data/
└── ip_addresses_sample/
    ├── 0.csv
    ├── 1.csv
    ├── 2.csv
    └── ...
```

Each CSV file corresponds to one IP address time series and should follow
the CESNET-TimeSeries24 format with columns:

```
id_time, n_flows, n_packets, n_bytes, n_dest_ip, n_dest_asn, n_dest_port,
tcp_udp_ratio_packets, tcp_udp_ratio_bytes, dir_ratio_packets,
dir_ratio_bytes, avg_duration, avg_ttl
```

## Where to get the data

Download `ip_addresses_sample.tar.gz` from:
https://zenodo.org/records/13382427

Then extract:
```bash
tar -xzf ip_addresses_sample.tar.gz
# Move the extracted CSVs into data/ip_addresses_sample/
```

The sample archive is ~171 MB (much smaller than the full 40 GB dataset).

## Aggregation level

The loader expects the 10-minute aggregation by default.
If your extracted files are nested under `agg_10_minutes/`, update
`DATA_DIR` in `config.py` to point to that subfolder.
