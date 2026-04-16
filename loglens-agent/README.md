# NCP LogLens — Syslog Event Intelligence & Natural-Language Q&A

**Track:** AI Agents for Network Operations (Automation / Observability)

LogLens turns natural-language questions into Splunk SPL queries, executes them,
and interprets the results as actionable summaries — no SPL expertise required.

---

## What It Does

### Syslog / Device Events
| You ask                                                                 | LogLens returns                                        |
|-------------------------------------------------------------------------|--------------------------------------------------------|
| "Show BGP flap events in the last 24h by peer and VRF"                  | Table: device, peer IP, VRF, flap count, time range   |
| "List authentication failures by username and device, past 6 hours"     | Table: device, username, failure count, first/last hit |
| "For leaf1, summarize interface events and BGP changes in the last 2h"  | Timeline + narrative for leaf1                        |
| "Explain repeated 'protocol identification string lack carriage return'" | Count by device + pattern explanation                 |
| "Give me a timeline of PSU and FAN events for Cisco-ONES on 2025-05-12" | Chronological event list with severities              |

Supported syslog categories: **BGP_FLAP · AUTH_FAILURE · IF_UP_DOWN · PSU_EVENT · FAN_EVENT · OSPF_EVENT · GENERIC_ERROR**

### Flow Telemetry (sFlow / NetFlow / IPFIX)
| You ask                                                        | LogLens returns                                          |
|----------------------------------------------------------------|----------------------------------------------------------|
| "Show top 10 source IPs by bytes in the last 24 hours"         | Table: src IP, total bytes, flow count                   |
| "What protocols are generating the most traffic this week?"    | Protocol distribution table with bytes and flow counts   |
| "Show all flows to or from 10.0.0.5 in the past hour"          | Table: src, dst, protocol, bytes per flow                |
| "Top source-destination pairs by flow count today"             | Ranked pairs table with bytes and counts                 |
| "Traffic volume trend over the last 7 days"                    | Hourly/daily bytes and flow count over time              |

Supported flow categories: **TOP_TALKERS · FLOW_PAIRS · PROTOCOL_DIST · TRAFFIC_TREND · IP_FLOWS**

---

## Architecture

```
LogLens Agent  (natural-language Q&A + interpretation)
    └── SplunkQueryAgent  (SPL generation + execution)
            ├── get_splunk_connection_info   — verify connectivity
            ├── list_indexes                 — discover all indexes + sourcetypes
            ├── discover_syslog_fields       — field schema for syslog/event data
            ├── discover_flow_fields         — field schema for sFlow/NetFlow/IPFIX
            └── search_splunk               — execute any SPL query
```

The **Query Agent** handles all SPL mechanics: it calls `list_indexes` to find
available data, picks `discover_syslog_fields` or `discover_flow_fields` based
on what the user is asking for, then builds and executes the SPL.
The **LogLens Agent** focuses on understanding intent and presenting results as
clear summaries.

No ingestion agent is needed — Splunk handles ingestion and indexing natively.

---

## Requirements

- Python 3.11+
- Splunk instance with syslog data indexed (UDP/TCP port 514)
- Splunk management API accessible (default port 8089)
- NCP SDK

### Data Inputs
- Syslog from NX-OS/IOS-XE, Arista EOS, SONiC devices (RFC 3164 / 5424)
- Flow telemetry logs: sFlow, NetFlow, IPFIX (any sourcetype indexed in Splunk)

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Splunk credentials
```bash
cp .env.example .env
# Edit .env with your Splunk host, port, and token/credentials
```

### 3. Deploy via NCP SDK
```bash
ncp deploy
```

Update `ncp.toml` with your NCP platform URL and API key before deploying.

---

## Configuration

| Environment Variable | Description                               | Default     |
|----------------------|-------------------------------------------|-------------|
| `SPLUNK_HOST`        | Splunk server hostname or IP              | `localhost` |
| `SPLUNK_PORT`        | Splunk management API port                | `8089`      |
| `SPLUNK_TOKEN`       | Bearer token (preferred)                  | —           |
| `SPLUNK_USERNAME`    | Username (fallback if no token)           | `admin`     |
| `SPLUNK_PASSWORD`    | Password (fallback if no token)           | `changeme`  |
| `SPLUNK_VERIFY_SSL`  | Verify TLS certificate (`true`/`false`)   | `false`     |

To generate a Splunk token: **Settings → Tokens → New Token** in Splunk Web.

---

## Example Questions

### Syslog / Device Events
```
Show BGP flap events in the last 24h by peer and VRF, with counts and timestamps.

List authentication failures by username and device in the past 6 hours.

For leaf1, summarize interface up/down events and BGP adjacency changes in the last 2 hours.

Explain repeated "protocol identification string lack carriage return" errors by device.

Give me a timeline of PSU and FAN events for Cisco-ONES on 2025-05-12.

Which devices generated the most error-level syslog events today?

Show all critical and emergency events from the last hour.
```

### Flow Telemetry
```
Show the top 10 source IPs by bytes in the last 24 hours.

What protocols are generating the most traffic this week?

Show all flows to or from 10.0.0.5 in the past hour.

Give me the top source-destination pairs by flow count today.

Show hourly traffic volume for the last 7 days.
```

---

## Success Criteria

| Metric                | Target                                                                          |
|-----------------------|---------------------------------------------------------------------------------|
| SPL generation        | ≥ 95 % correct translation from NL prompts                                      |
| Interpretation        | ≥ 95 % of summaries match manually derived insights                             |
| Syslog categories     | BGP_FLAP, AUTH_FAILURE, IF_UP_DOWN, PSU_EVENT, FAN_EVENT, OSPF_EVENT           |
| Flow categories       | TOP_TALKERS, FLOW_PAIRS, PROTOCOL_DIST, TRAFFIC_TREND, IP_FLOWS                |
| Latency               | ≤ 3 s question → summarized result at 500 logs/sec                              |

---

## Project Structure

```
loglens-agent/
├── agents/
│   ├── __init__.py
│   └── main.py          # SplunkQueryAgent + LogLens (main entry point)
├── tools/
│   ├── __init__.py
│   └── splunk_tools.py  # Splunk REST API tools
├── .env.example         # Environment variable template
├── .gitignore
├── ncp.toml             # NCP deployment config
├── requirements.txt
└── README.md
```
