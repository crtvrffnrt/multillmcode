# MultiLLM Orchestrator

A modular helper framework for orchestrating multiple Large Language Model (LLM) CLI agents to perform complex, multi-step tasks. This tool decomposes goals into actionable tasks, assigns them to specialized agents (Gemini, Codex, Claude), and manages the execution flow with integrated policy enforcement and audited logging.

## Prerequisites

Before using the MultiLLM Orchestrator, ensure you have the following CLI tools installed and authenticated:

### 1. Gemini CLI
The Gemini CLI is used for analytical interpretation and summarization.
- **Login:** Follow the on-screen prompts during your first run or use the standard authentication method provided by your environment.
- This project launches Gemini in headless `--prompt` mode with `--approval-mode yolo` so runs do not pause for approvals.

### 2. Codex CLI
The Codex CLI is the primary agent for code generation and technical implementation.
- **Login:**
  ```bash
  codex login
  ```
  Follow the browser-based OAuth flow or use `--with-api-key` if required.
- This project launches Codex with `--dangerously-bypass-approvals-and-sandbox` so it can run unattended with full local access.

### 3. Claude Code CLI
Claude is used for architectural review and security policy validation.
- **Login:**
  ```bash
  claude auth login
  ```
- This project launches Claude in `--print` mode with `--dangerously-skip-permissions` enabled so it can complete non-interactively.

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
- The default prompt wrapper exports `MULTILLM_ALLOW_ALL_TARGETS=1`, `MULTILLM_UNATTENDED=1`, `CI=1`, and `NONINTERACTIVE=1` so the tool runs without user interaction unless you override those variables.

## Usage

Run the orchestrator with a high-level goal:

```bash
python3 core/orchestrator.py "Execute an nmap scan on 127.0.0.1 and analyze the results for vulnerabilities."
```

For a single prompt with live streaming output:

```bash
chmod +x prompt.sh
./prompt.sh "what is 1+1"
```

### Directory Structure
- `core/`: The central orchestration logic.
- `configs/`: Agent and security policy definitions.
- `wrappers/`: Audited shell wrappers for agent execution.
- `logs/runs/<run_id>/`: Detailed audit logs, stdout, stderr, and incremental event logs for each run.
- `runs/`: JSON-formatted execution records and metadata.

## Security & Auditing
Every command executed by an agent is passed through `wrappers/agent_exec.sh`, which logs the exact command, start/end times, exit codes, and full output into a run-scoped directory under `logs/runs/<run_id>/`. The orchestrator enforces the `policy.yaml` rules before any task is dispatched to an agent and prepends the shared instruction block plus the global skill registry to each agent prompt.

If your shared skills live somewhere other than `~/.agents/skills`, set `MULTILLM_SKILLS_DIR` before running the CLI:

```bash
export MULTILLM_SKILLS_DIR="$HOME/.agents/skills"
./prompt.sh "..."
```
