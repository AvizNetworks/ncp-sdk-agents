# NCP SDK Agents

**Learn by doing: hands-on examples for building AI agents with the NCP SDK**

This repository contains complete, working SDK agents that demonstrate how to build AI agents using the [NCP SDK](https://docs.google.com/document/d/1dge4J665P3SigTRK3RAHm0sZ1U3niYx6XwpatqoJC14/edit?tab=t.0#heading=h.49a6698begdo). 
---

### Each Agent must Includes

- ✅ **Comprehensive README**: Step-by-step Guide
- ✅ **Complete Code**: Production-ready, commented
- ✅ **Project Structure**: Standard NCP SDK layout
- ✅ **Example Interactions**: See what it does
- ✅ **Key Takeaways**: What you learned
- ✅ **Next Steps**: How to extend it

### Running an Example

```bash
# Navigate to the example
cd <example-name>

# Install dependencies
pip install -r requirements.txt

# Validate the project
ncp validate .

# Deploy to platform
ncp authenticate
ncp package .
ncp deploy <example-name>.ncp
```

---

## 🛠️ Development Workflow

### Common Commands

```bash
# Validate your agent
ncp validate .

# Package for deployment
ncp package .

# Authenticate with platform
ncp authenticate

# Deploy to platform
ncp deploy <agent>.ncp

# Test interactively
ncp playground --agent <agent-name>

# Remove agent
ncp remove --agent <agent-name>
```

