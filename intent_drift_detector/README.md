# Intent Drift Detector

An AI-powered agent that detects configuration drift between intended state and actual running state of network devices. Supports **two platforms**:

1. **ONES Fabric Manager (onesfm)** - Aviz Networks' fabric management platform
2. **Cisco Nexus Dashboard Fabric Controller (NDFC)** - Cisco's data center fabric controller

## Overview

In production networks, operators may:
- Push out-of-band configs (manual CLI changes)
- Experience partial config failures during rollout
- Have drift introduced by automation bugs

This agent automates the detection of such drift by:
1. Fetching intended configuration from **GitHub URL** (user-provided YAML)
2. Fetching live running configuration from devices (ONES FM or NDFC)
3. Comparing intended vs actual state
4. Generating detailed drift reports with severity levels

## Supported Platforms

### ONES Fabric Manager (onesfm)

ONES FM exposes tools via its MCP server for fetching device configurations:

| Tool | Description |
|------|-------------|
| `fetch_running_config` | Fetch current running config from a device by IP |

**Workflow**: User provides GitHub URL with intent → Agent fetches running configs from devices → Compares and reports drift.

### Nexus Dashboard Fabric Controller (NDFC)

NDFC provides REST APIs for fabric management:

| Tool | Description |
|------|-------------|
| `login_to_ndfc` | Authenticate with Nexus Dashboard |
| `get_fabric_switches` | Get switches in a fabric |
| `get_all_interfaces` | Get interface configurations |
| `get_fabric_vrfs` | Get VRF definitions |
| `get_fabric_networks` | Get VXLAN network definitions |
| `get_portchannels` | Get port-channel configurations |
| `get_switch_policies` | Get policies applied to switches |
| `get_complete_fabric_state` | Get all fabric data in one call |

**Workflow**: User provides GitHub URL with intent → Agent fetches running state from NDFC → Compares and reports drift.

## Intent Management Tools (Common to Both Platforms)

| Tool | Description |
|------|-------------|
| `fetch_intent_from_github` | Fetch intent YAML file from a GitHub URL |
| `get_sample_intent_template` | Get a sample intent template for users to customize |
| `parse_intent_yaml` | Parse intent YAML content |
| `compare_intent_vs_running` | Compare and detect configuration drifts |
| `generate_drift_report_markdown` | Generate formatted Markdown report |

## Project Structure

```
intent_drift_detector/
├── ncp.toml              # Project configuration
├── requirements.txt      # Python dependencies
├── apt-requirements.txt  # System dependencies (optional)
├── agents/
│   └── main_agent.py     # Main agent with platform tools
├── tools/
│   ├── __init__.py       # Tool exports & MCP server config
│   ├── ndfc_tools.py     # NDFC API integration
│   └── ones_tools.py     # ONES FM MCP integration
├── samples/
│   └── sample_intent.yaml # Sample intent file template
└── docs/
    ├── NDFC_API_Research.md        # API documentation
    └── NDFC_API_Analysis_Final.md  # API test results
```

## Architecture 

```
┌─────────────────────────────────────────────────────────────┐
│                   Intent Drift Detector                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Intent Source: GitHub URL                   │  │
│  │  • fetch_intent_from_github                           │  │
│  │  • get_sample_intent_template                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↓                                  │
│  ┌─────────────────────┐     ┌─────────────────────────┐   │
│  │  ONES Fabric Manager │     │  Nexus Dashboard (NDFC) │   │
│  │      (onesfm)        │     │                         │   │
│  ├─────────────────────┤     ├─────────────────────────┤   │
│  │ MCP Server Tools:    │     │ REST API Tools:         │   │
│  │ • fetch_running_     │     │ • login_to_ndfc         │   │
│  │   config             │     │ • get_fabric_switches   │   │
│  │                      │     │ • get_all_interfaces    │   │
│  │                      │     │ • get_fabric_vrfs       │   │
│  │                      │     │ • get_complete_fabric_  │   │
│  └─────────────────────┘     │   state                 │   │
│                               └─────────────────────────┘   │
│                           ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Drift Detection & Reporting                │  │
│  │  • parse_intent_yaml                                  │  │
│  │  • compare_intent_vs_running                          │  │
│  │  • generate_drift_report_markdown                     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```


## Features

### Drift Detection Tools (Common)

| Tool | Description |
|------|-------------|
| `parse_intent_yaml` | Parse user-provided intent YAML |
| `compare_intent_vs_running` | Compare and detect configuration drifts |
| `generate_drift_report_markdown` | Generate formatted Markdown report |

### Drift Categories

- **🔴 Critical**: Service-affecting issues (admin state, IP addresses)
- **🟠 Major**: Potential issues (MTU mismatch, mode mismatch)
- **🟡 Minor**: Cosmetic differences (descriptions)

## Intent YAML Format

Create an intent file defining your desired configuration:

```yaml
intent:
  name: "Production Fabric Intent"
  version: "1.0"

fabric:
  name: "NCP-Eng"

devices:
  - hostname: "leaf-01"
    role: "leaf"
    management_ip: "10.4.6.21"
    nxos_version: "9.3(9)"

interfaces:
  - device: "leaf-01"
    name: "Ethernet1/1"
    admin_state: "up"
    mtu: 9216
    mode: "trunk"
    allowed_vlans: "100-200"
    
  - device: "leaf-01"
    name: "Loopback0"
    ip_address: "10.2.0.1/32"

port_channels:
  - device: "leaf-01"
    name: "port-channel10"
    mode: "trunk"
    members: ["Ethernet1/10", "Ethernet1/11"]

vrfs:
  - name: "PROD_VRF"
    vni: 50001
    devices: ["leaf-01", "leaf-02"]

networks:
  - name: "PROD_NET_100"
    vni: 30100
    vlan: 100
    vrf: "PROD_VRF"
    gateway: "10.100.1.1/24"
```

See `samples/sample_intent.yaml` for a complete example.

## Quick Start

### 1. Authenticate with Platform

```bash
ncp authenticate
```

### 2. Validate Project

```bash
ncp validate .
```

### 3. Package Agent

```bash
ncp package .
```

### 4. Deploy Agent

```bash
# First deployment
ncp deploy intent_drift_detector.ncp

# Update existing agent
ncp deploy intent_drift_detector.ncp --update
```

### 5. Test in Playground

```bash
ncp playground --agent intent_drift_detector 
```

## Usage Examples

### Getting Started with Intent Files

**Get a sample intent template:**
```
I need a sample intent file to get started. Can you give me a template?
```

**After customizing, upload to GitHub and run drift detection.**

### ONES Fabric Manager Examples

**Check drift with GitHub intent file:**
```
Check for configuration drift in my ONES-managed fabric.
My intent file is at: https://github.com/myorg/network-intents/blob/main/prod-fabric-intent.yaml
Device IPs: 10.4.6.21, 10.4.6.22
```

**Check specific device:**
```
Fetch the running config from device 10.4.6.21 and compare it 
against my intent file at: https://github.com/myorg/intents/blob/main/leaf01.yaml
```

### NDFC Examples

**Full drift detection workflow with GitHub intent:**
```
I want to check if my NDFC fabric matches my intended configuration.
NDFC host: 10.4.4.184
Username: admin
Password: mypassword
Fabric: NCP-Eng
Intent file: https://github.com/myorg/network-intents/blob/main/ncp-eng-intent.yaml
```

**Login to NDFC:**
```
Login to NDFC at 10.4.4.184 with username admin and password mypassword
```

**Get fabric inventory:**
```
Show me all switches in the NCP-Eng fabric
```

**Specific checks:**
```
Get all interfaces for switch with serial FOC2020R1E7
```

```
Show me the VRFs configured in fabric NCP-Eng
```

### Sample Drift Report Output

```markdown
# Intent Drift Detection Report

## Summary

| Metric | Value |
|--------|-------|
| Total Checks | 15 |
| Passed | 12 |
| Critical Drifts | 1 |
| Major Drifts | 2 |
| Minor Drifts | 0 |
| **Compliance** | **80%** |

## ❌ Drifts Detected

### 🔴 Critical Drifts

| Device | Type | Field | Intended | Running |
|--------|------|-------|----------|---------|
| leaf-01/Ethernet1/1 | interface | admin_state | `up` | `down` |

### 🟠 Major Drifts

| Device | Type | Field | Intended | Running |
|--------|------|-------|----------|---------|
| leaf-01/Ethernet1/2 | interface | mtu | `9216` | `1500` |
| leaf-02 | device | role | `leaf` | `spine` |
```

## Configuration

### requirements.txt

```
requests>=2.28.0
urllib3>=2.0.0
pyyaml>=6.0
```

### ncp.toml

```toml
[project]
name = "intent_drift_detector"
version = "0.1.0"
description = "AI-powered intent drift detection for NDFC fabrics"

[build]
python_version = "3.11"
entry_point = "agents.main_agent:agent"
```

## Supported NDFC APIs

Based on testing, the following NDFC APIs are used:

| API | Status | Purpose |
|-----|--------|---------|
| `POST /login` | ✅ | Authentication |
| `GET /control/fabrics/{fabric}/inventory` | ✅ | Switch inventory |
| `GET /interface/detail` | ✅ | Interface configs |
| `GET /top-down/fabrics/{fabric}/vrfs` | ✅ | VRF definitions |
| `GET /top-down/fabrics/{fabric}/networks` | ✅ | VXLAN networks |
| `GET /interface/detail?ifType=INTERFACE_PORT_CHANNEL` | ✅ | Port-channels |
| `GET /control/policies/switches/{sn}` | ✅ | Switch policies |

See `docs/NDFC_API_Analysis_Final.md` for detailed API documentation.

## Development

### Adding New Comparison Logic

Edit `agents/main_agent.py` and extend the `compare_intent_vs_running` function:

```python
# Example: Add VRF comparison
for vrf in intent_data.get("vrfs", []):
    vrf_name = vrf.get("name")
    # Compare against running_data["vrfs"]
    # Add drift entries as needed
```

### Adding New NDFC Tools

1. Add the function to `tools/ndfc_tools.py`
2. Export it in `tools/__init__.py`
3. Create a wrapper with `@tool` decorator in `agents/main_agent.py`
4. Add to the agent's `tools` list

## Troubleshooting

### NDFC Connection Issues

- Verify NDFC host is reachable
- Check credentials are correct
- Ensure SSL certificates are valid (or tool handles self-signed certs)

### Empty Results

- Confirm fabric name is correct
- Check if switches are discovered in NDFC
- Verify user has appropriate NDFC permissions

### Validation Errors

```bash
ncp validate .
```

Check for:
- Python syntax errors
- Missing dependencies
- Import issues

