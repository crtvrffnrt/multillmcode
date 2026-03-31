import os
import sys
import yaml
import json
import uuid
import subprocess
import re
import shlex
from datetime import datetime
from pathlib import Path

try:
    from core.guidance import RED_TEAM_GUIDANCE, format_skill_catalog, load_skill_catalog
except ImportError:
    from guidance import RED_TEAM_GUIDANCE, format_skill_catalog, load_skill_catalog

class MultiLLMOrchestrator:
    def __init__(self, root_dir=None):
        if root_dir is None:
            # Default to the parent directory of this script's location
            self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        else:
            self.root_dir = os.path.abspath(root_dir)
            
        self.configs_dir = os.path.join(self.root_dir, "configs")
        self.runs_dir = os.path.join(self.root_dir, "runs")
        self.logs_dir = os.path.join(self.root_dir, "logs")
        self.wrapper_path = os.path.join(self.root_dir, "wrappers", "agent_exec.sh")
        self.run_logs_root = os.path.join(self.logs_dir, "runs")
        
        # Ensure directories exist
        for d in [self.runs_dir, self.logs_dir, self.run_logs_root]:
            if not os.path.exists(d):
                os.makedirs(d)

        self.agents = self._load_yaml("agents.yaml")["agents"]
        self.policy = self._load_yaml("policy.yaml")["policy"]
        self.skill_catalog = load_skill_catalog()
        self.skill_catalog_text = format_skill_catalog(self.skill_catalog)
        self.prompt_prefix = self._build_prompt_prefix()
        self.agent_names = [agent["name"] for agent in self.agents]
        
    def _load_yaml(self, filename):
        path = os.path.join(self.configs_dir, filename)
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def _build_prompt_prefix(self):
        return "\n\n".join(
            [
                RED_TEAM_GUIDANCE.strip(),
                self.skill_catalog_text.strip(),
                "Operational rule: choose the narrowest relevant skill for the current phase and keep work incremental, evidence-based, and reproducible.",
            ]
        )

    def _append_jsonl(self, path, payload):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _run_dir(self, run_id):
        return os.path.join(self.run_logs_root, run_id)

    def _run_event_log_path(self, run_id):
        return os.path.join(self._run_dir(run_id), "events.jsonl")

    def _build_prompt(self, prompt):
        return f"{self.prompt_prefix}\n\nUser task:\n{prompt}"

    def is_authorized(self, target):
        return target in self.policy["authorized_targets"]

    def _decompose_with_agent(self, goal, run_id, run_dir):
        decomposition_prompt = f"""Decompose the following user goal into a task graph for specialized agents.
User Goal: {goal}

Available Agents:
- codex: implementation, scripting, CLI execution.
- gemini: analysis, interpretation, summarization.
- claude: architecture review, policy validation, security assessment.

Output a JSON array of tasks. Each task MUST have:
- id: unique string
- agent: one of [codex, gemini, claude]
- prompt: the specific instruction for the agent
- depends_on: (optional) list of task IDs this task depends on
- target: (optional) IP or hostname if the task interacts with a specific target

Example:
[
  {{"id": "recon", "agent": "codex", "prompt": "Scan 127.0.0.1 for open ports", "target": "127.0.0.1"}},
  {{"id": "analyze", "agent": "gemini", "prompt": "Identify risks in the scan results", "depends_on": ["recon"]}}
]

Return ONLY the JSON array."""
        
        print("[*] Requesting dynamic decomposition from gemini...", flush=True)
        result = self.execute_with_failover("gemini", decomposition_prompt, run_id, run_dir)
        
        stdout = result.get("stdout", "")
        # Extract JSON array from output
        match = re.search(r'\[\s*\{.*\}\s*\]', stdout, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        
        print("[!] Dynamic decomposition failed or returned invalid JSON. Using static rules.", flush=True)
        return []

    def decompose_goal(self, goal, run_id=None, run_dir=None):
        """Task graph decomposition logic."""
        # First check static rules for common patterns
        tasks = []
        target_match = re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|localhost', goal)
        target = target_match.group(0) if target_match else "unknown"

        if ("scan" in goal.lower() or "ports" in goal.lower()) and target != "unknown":
            tasks = [
                {
                    "id": "t1_recon",
                    "agent": "codex",
                    "action": "IMPLEMENTATION",
                    "prompt": f"Execute an nmap service scan on {target}. Use: nmap -sV -Pn {target}",
                    "target": target
                },
                {
                    "id": "t2_interpret",
                    "agent": "gemini",
                    "action": "INTERPRETATION",
                    "prompt": "Analyze the following scan results and identify potentially vulnerable services: ",
                    "depends_on": ["t1_recon"]
                },
                {
                    "id": "t3_validate",
                    "agent": "claude",
                    "action": "ARCHITECTURE",
                    "prompt": "Review the identified risks and suggest 3 passive reconnaissance steps to further analyze the target without alerting defense systems.",
                    "depends_on": ["t2_interpret"]
                }
            ]
        
        # If no static rule matched and we have a run context, try dynamic decomposition
        if not tasks and run_id and run_dir:
            tasks = self._decompose_with_agent(goal, run_id, run_dir)
            
        return tasks

    def extract_metadata(self, raw_output):
        """Extracts framework metadata from agent output noise."""
        try:
            pattern = r"___FRAMEWORK_METADATA_START___\s*(\{.*?\})\s*___FRAMEWORK_METADATA_END___"
            match = re.search(pattern, raw_output, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            return None
        except Exception:
            return None

    def _is_retryable_failure(self, result):
        exit_code = result.get("exit_code")
        if exit_code == 0 and not result.get("error"):
            return False
        if exit_code in (126, 127):
            return True

        text_parts = []
        for key in ("error", "raw", "stderr", "stdout"):
            value = result.get(key)
            if isinstance(value, str):
                text_parts.append(value)
        blob = "\n".join(text_parts).lower()

        retryable_markers = [
            "quota",
            "rate limit",
            "resource_exhausted",
            "exhausted your capacity",
            "out of tokens",
            "token limit",
            "context length",
            "context window",
            "backenderror",
            "internal error",
            "service unavailable",
            "temporarily unavailable",
            "too many requests",
            "command not found",
            "permission denied",
            "429",
            "500",
        ]

        return any(marker in blob for marker in retryable_markers)

    def _failure_reason(self, result):
        text_parts = []
        for key in ("error", "raw", "stderr"):
            value = result.get(key)
            if isinstance(value, str):
                text_parts.append(value)
        blob = "\n".join(text_parts).strip()
        if not blob:
            return "unknown failure"
        first_line = blob.splitlines()[0].strip()
        return first_line[:240]

    def _fallback_chain(self, primary_agent):
        ordered = []
        seen = set()
        for name in [primary_agent] + self.agent_names:
            if name not in seen and name in self.agent_names:
                ordered.append(name)
                seen.add(name)
        return ordered

    def execute_agent(self, agent_name, prompt, run_id, run_dir=None):
        agent_cfg = next((a for a in self.agents if a["name"] == agent_name), None)
        if not agent_cfg:
            raise ValueError(f"Agent {agent_name} not registered.")

        # Construct CLI call
        full_command = f"{agent_cfg['default_cmd']} {shlex.quote(self._build_prompt(prompt))}"
        effective_run_dir = run_dir or self._run_dir(run_id)
        
        try:
            # Execute via audited wrapper and relay output live.
            process = subprocess.Popen(
                [self.wrapper_path, agent_name, full_command, run_id, effective_run_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            collected = []
            assert process.stdout is not None
            for line in iter(process.stdout.readline, ""):
                collected.append(line)
                sys.stdout.write(line)
                sys.stdout.flush()

            process.stdout.close()
            return_code = process.wait()
            output = "".join(collected)
            
            metadata = self.extract_metadata(output)
            if not metadata:
                # Fallback: metadata was likely suppressed or agent failed to output it
                return {"error": "Metadata extraction failed", "raw": output, "exit_code": return_code}
            metadata["stdout"] = output
            return metadata
        except Exception as e:
            return {"error": str(e)}

    def execute_with_failover(self, preferred_agent, prompt, run_id, run_dir):
        attempts = []
        for agent_name in self._fallback_chain(preferred_agent):
            print(f"[>] Attempting {agent_name} for this step.", flush=True)
            self._append_jsonl(
                self._run_event_log_path(run_id),
                {
                    "event": "attempt_start",
                    "timestamp": datetime.now().isoformat(),
                    "agent": agent_name,
                    "preferred_agent": preferred_agent,
                },
            )
            result = self.execute_agent(agent_name, prompt, run_id, run_dir=run_dir)
            # Create a copy for the history to avoid circular reference
            attempt_record = dict(result)
            attempt_record["agent"] = agent_name
            attempts.append(attempt_record)

            self._append_jsonl(
                self._run_event_log_path(run_id),
                {
                    "event": "attempt_end",
                    "timestamp": datetime.now().isoformat(),
                    "agent": agent_name,
                    "preferred_agent": preferred_agent,
                    "exit_code": result.get("exit_code"),
                    "retryable": self._is_retryable_failure(result),
                    "error": result.get("error"),
                },
            )

            if result.get("exit_code") == 0 and not result.get("error"):
                if agent_name != preferred_agent:
                    print(f"[*] Fallback used: {preferred_agent} -> {agent_name}", flush=True)
                
                final_result = dict(result)
                final_result["agent"] = agent_name
                final_result["preferred_agent"] = preferred_agent
                final_result["attempts"] = attempts
                return final_result

            if self._is_retryable_failure(result):
                reason = self._failure_reason(result)
                print(f"[!] {agent_name} hit a retryable failure ({reason}); falling back.", flush=True)
                continue

            break

        return {
            "error": "All agent attempts failed",
            "preferred_agent": preferred_agent,
            "attempts": attempts,
            "agent": attempts[-1].get("agent") if attempts else "none",
            "exit_code": attempts[-1].get("exit_code") if attempts else 1
        }

    def run(self, goal):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        run_path = os.path.join(self.runs_dir, f"{run_id}.json")
        run_dir = self._run_dir(run_id)
        os.makedirs(run_dir, exist_ok=True)
        event_log_path = self._run_event_log_path(run_id)
        
        print(f"[*] Starting RUN: {run_id}", flush=True)
        print(f"[*] Goal: {goal}", flush=True)
        self._append_jsonl(
            event_log_path,
            {
                "event": "run_start",
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "goal": goal,
            },
        )
        
        tasks = self.decompose_goal(goal, run_id, run_dir)
        run_log = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "goal": goal,
            "run_dir": run_dir,
            "event_log": event_log_path,
            "tasks": []
        }

        task_outputs = {}
        if not tasks:
            print("[*] No decomposition tasks matched; running a single prompt through gemini.", flush=True)
            result = self.execute_with_failover("gemini", goal, run_id, run_dir)
            run_log["tasks"].append({
                "task_id": "prompt",
                "agent": result.get("agent", "gemini"),
                "preferred_agent": "gemini",
                "metadata": result,
                "timestamp": datetime.now().isoformat()
            })
        else:
            for task in tasks:
                print(f"[>] Executing Task: {task['id']} ({task['agent']})", flush=True)
                self._append_jsonl(
                    event_log_path,
                    {
                        "event": "task_start",
                        "task_id": task["id"],
                        "agent": task["agent"],
                        "timestamp": datetime.now().isoformat(),
                    },
                )
            
                if "target" in task and not self.is_authorized(task["target"]):
                    print(f"[!] REJECTED: Target {task['target']} is not in scope.", flush=True)
                    task["status"] = "REJECTED_BY_POLICY"
                    self._append_jsonl(
                        event_log_path,
                        {
                            "event": "task_rejected",
                            "task_id": task["id"],
                            "agent": task["agent"],
                            "target": task["target"],
                            "timestamp": datetime.now().isoformat(),
                        },
                    )
                    continue

                # Build context from dependencies
                context_buffer = ""
                dependencies = task.get("depends_on", [])
                if isinstance(dependencies, str):
                    dependencies = [dependencies]
                    
                for dep_id in dependencies:
                    if dep_id in task_outputs:
                        context_buffer += f"\n--- PRIOR OUTPUT ({dep_id}) ---\n" + task_outputs[dep_id]

                current_prompt = task["prompt"] + context_buffer
                result = self.execute_with_failover(task["agent"], current_prompt, run_id, run_dir)
            
                # Update task outputs from result
                if "stdout_path" in result and os.path.exists(result["stdout_path"]):
                    with open(result["stdout_path"], "r") as f:
                        task_outputs[task["id"]] = f.read()

                run_log["tasks"].append({
                    "task_id": task["id"],
                    "agent": task["agent"],
                    "metadata": result,
                    "timestamp": datetime.now().isoformat()
                })
                self._append_jsonl(
                    event_log_path,
                    {
                        "event": "task_end",
                        "task_id": task["id"],
                        "agent": result.get("agent", task["agent"]),
                        "timestamp": datetime.now().isoformat(),
                        "exit_code": result.get("exit_code"),
                    },
                )
            
                if result.get("exit_code") != 0:
                    print(f"[!] Warning: Task {task['id']} failed with code {result.get('exit_code')}", flush=True)

        # Save run record
        with open(run_path, "w") as f:
            json.dump(run_log, f, indent=2)

        # Final summary
        print(f"[*] Generating run summary...", flush=True)
        summary_prompt = f"Provide a brief, high-level summary of the entire run for the goal: {goal}\n\nTasks and outcomes:\n"
        for t in run_log["tasks"]:
             status = "Success" if t["metadata"].get("exit_code") == 0 else "Failed"
             summary_prompt += f"- Task {t['task_id']} ({t['agent']}): {status}\n"
        
        summary_result = self.execute_with_failover("gemini", summary_prompt, run_id, run_dir)
        print("\n=== RUN SUMMARY ===")
        print(summary_result.get("stdout", "No summary generated."))
        print("===================\n")

        self._append_jsonl(
            event_log_path,
            {
                "event": "run_end",
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "run_path": run_path,
            },
        )
            
        print(f"[*] Run Complete. Metadata: {run_path}", flush=True)
        return run_log

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 orchestrator.py '<goal>'")
    else:
        orchestrator = MultiLLMOrchestrator()
        orchestrator.run(" ".join(sys.argv[1:]))
