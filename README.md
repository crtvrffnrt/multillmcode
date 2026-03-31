# MultiLLM Orchestrator

A modular helper framework for orchestrating multiple Large Language Model (LLM) CLI agents to perform complex, multi-step tasks. This tool decomposes goals into actionable tasks, assigns them to specialized agents (Gemini, Codex, Claude), and manages the execution flow with integrated policy enforcement and audited logging.

## Prerequisites

Before using the MultiLLM Orchestrator, ensure you have the following CLI tools installed and authenticated:

### 1. Gemini CLI
The Gemini CLI is used for analytical interpretation and summarization.
- **Login:** Follow the on-screen prompts during your first run or use the standard authentication method provided by your environment.

### 2. Codex CLI
The Codex CLI is the primary agent for code generation and technical implementation.
- **Login:**
  ```bash
  codex login
  ```
  Follow the browser-based OAuth flow or use `--with-api-key` if required.

### 3. Claude Code CLI
Claude is used for architectural review and security policy validation.
- **Login:**
  ```bash
  claude auth login
  ```

## Installation

1. Clone the repository:
   ```bash
   git clone git@github.com:crtvrffnrt/multillmcode.git
   cd multillmcode
   ```

2. Install dependencies:
   ```bash
   pip install pyyaml
   ```

3. Ensure the execution wrapper is executable:
   ```bash
   chmod +x wrappers/agent_exec.sh
   ```

## Configuration

### Agents (`configs/agents.yaml`)
Define the CLI commands and roles for each agent. You can customize the `default_cmd` to include specific flags or sandboxing options.

### Policy (`configs/policy.yaml`)
Configure the safety boundaries:
- `authorized_targets`: List of IPs or hostnames the agents are allowed to interact with.
- `authorized_modes`: Allowed operation types (e.g., BUILD, ANALYZE).
- `require_approval`: Actions that trigger a mandatory human-in-the-loop check.

## Usage

Run the orchestrator with a high-level goal:

```bash
python3 core/orchestrator.py "Execute an nmap scan on 127.0.0.1 and analyze the results for vulnerabilities."
```

### Directory Structure
- `core/`: The central orchestration logic.
- `configs/`: Agent and security policy definitions.
- `wrappers/`: Audited shell wrappers for agent execution.
- `logs/`: Detailed audit logs, stdout, and stderr for every agent interaction.
- `runs/`: JSON-formatted execution records and metadata.

## Security & Auditing
Every command executed by an agent is passed through `wrappers/agent_exec.sh`, which logs the exact command, start/end times, exit codes, and full output. The orchestrator enforces the `policy.yaml` rules before any task is dispatched to an agent.
