"""Main agent definition."""

from ncp import Agent
from tools.network_tools import (
    list_supported_intents,
    get_intent_template,
    parse_bgp_intent,
    validate_bgp_intent,
    generate_intent_yaml,
    check_ansible_installed,
    run_ansible_bgp,
    check_existing_bgp_connection,
    check_bgp_status,
    remove_bgp_configuration,
    parse_vlan_intent,
    run_ansible_vlan,
    remove_vlan,
    list_vlans
)

from ncp import LLMConfig

agent = Agent(

    name="BgpIntentAgent",

    description="""
AI Network Automation Agent that generates BGP intent
and configures routers using Ansible automation.
""",

    instructions="""

You are a Network Automation AI Agent.

Workflow for BGP Intent:

1. Parse request using parse_bgp_intent.

2. If user asks about existing BGP:
   → run check_existing_bgp_connection

3. If user asks to create BGP:
   → validate intent
   → check_existing_bgp_connection
   → if not present run run_ansible_bgp
   → verify with check_bgp_status

4. If user asks to remove BGP:
   → run remove_bgp_configuration

Workflow for VLAN Intent:
1. Parse request using parse_vlan_intent.
2. Validate VLAN ID is between 1 and 4094.
3. Configure VLAN on specified switches using run_ansible_vlan.
4. To remove VLAN, run remove_vlan.
5. To list VLANs, run list_vlans.


Rules:

- Default ASN = 1001 if not provided
- Always validate intent before configuration
- Use Ansible ad-hoc commands (no playbooks)
- Disable SSH host key checking
""",

    tools=[
        list_supported_intents,
        get_intent_template,
        parse_bgp_intent,
        validate_bgp_intent,
        generate_intent_yaml,
        check_ansible_installed,
        run_ansible_bgp,
        check_existing_bgp_connection,
        check_bgp_status,
        remove_bgp_configuration,
        parse_vlan_intent,
        run_ansible_vlan,
        remove_vlan,
        list_vlans
    ],

    llm_config=LLMConfig(
        temperature=0
    )
)