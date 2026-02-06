# NCP SDK Quick Start README

## Overview
The **NCP SDK** is a Python framework for building AI agents on the **Network Copilot Platform (NCP)**. Create agents for network troubleshooting, monitoring, automation, and NL queries using tools, MCP integration, and async patterns.

**Capabilities**: Log analysis, device health checks, incident response, inventory reports, Splunk searches, trend analysis.

## Prerequisites
- Python 3.9+
- NCP platform account
- Basic Python (functions, decorators)

## Quick Start Steps

1. **Install SDK**
   ```
   pip install ncp-sdk
   ```

2. **Init Project**
   ```
   ncp init my-agent
   cd my-agent
   ```

3. **Build Agent** (agents/main_agent.py)
   ```python
   from ncp import Agent, tool

   @tool
   def say_hello(name: str) -> str:
       """Greet by name."""
       return f"Hello, {name}!"

   agent = Agent(
       name="HelloAgent",
       description="Greeting assistant",
       instructions="Greet people using say_hello tool.",
       tools=[say_hello]
   )
   ```

4. **Validate & Package**
   ```
   ncp validate .
   ncp package .  # Creates my-agent.ncp
   ```

5. **Deploy & Test**
   ```
   ncp deploy my-agent.ncp --platform <URL>
   ncp playground <agent-id> --platform <URL>
   ```

## Core Concepts
- **Tools**: `@tool`-decorated functions with type hints/docstrings.
- **Agents**: Combine LLM + tools + instructions for workflows.
- **Async**: Use `async def` + `asyncio.gather` for I/O (e.g., batch device checks).
- **MCP**: Connect to external tool servers (plug-and-play).

## Project Structure
```
my-agent/
├── ncp.toml          # Config
├── agents/           # Agent definitions
├── tools/            # @tool functions
├── tests/            # Tool tests
└── requirements.txt  # Dependencies
```

## Next Steps
- **Full Guide**: Parts 1-6 cover tools, MCP, NetOps examples.
- **Examples Repo**: Hands-on network agents (metrics, logs).
- **CLI**: `ncp --help` for auth, build, deploy.

Deploy your first agent in <5 mins! 🚀

## NCP Agents
- **Agent MO(memory Observer)**: AgentMo is an AI agent that provides fabric-wide memory observability by monitoring utilization across devices and key services, enabling early detection of memory bloat and leaks.
- **sonic-dump-analysis-agent**: An AI agent that ingests and analyzes Zendesk tickets, analyzes and correlates tech-support dump data with internal KB similarity matches, and delivers deterministic RCA with recommended remediation steps.
