"""Custom tools for intent_drift_detector."""

from ncp import MCPConfig

sse_server = MCPConfig(
    transport_type ="sse",
    url="http://10.4.5.113:4321/sse"
)