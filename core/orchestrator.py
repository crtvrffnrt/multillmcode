import os
import sys
import yaml
import json
import uuid
import subprocess
import re
from datetime import datetime

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
        
        # Ensure directories exist
        for d in [self.runs_dir, self.logs_dir]:
            if not os.path.exists(d):
                os.makedirs(d)

        self.agents = self._load_yaml("agents.yaml")["agents"]
        self.policy = self._load_yaml("policy.yaml")["policy"]
        
    def _load_yaml(self, filename):
        path = os.path.join(self.configs_dir, filename)
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def is_authorized(self, target):
        return target in self.policy["authorized_targets"]

    def decompose_goal(self, goal):
        """Simple task graph decomposition logic."""
        tasks = []
        # Pattern matching for lab targets
        target_match = re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|localhost', goal)
        target = target_match.group(0) if target_match else "unknown"

        if "scan" in goal.lower() or "ports" in goal.lower():
            tasks.append({
                "id": "t1_recon",
                "agent": "codex",
                "action": "IMPLEMENTATION",
                "prompt": f"Execute an nmap service scan on {target}. Use: nmap -sV -Pn {target}",
                "target": target
            })
            tasks.append({
                "id": "t2_interpret",
                "agent": "gemini",
                "action": "INTERPRETATION",
                "prompt": "Analyze the following scan results and identify potentially vulnerable services: ",
                "depends_on": "t1_recon"
            })
            tasks.append({
                "id": "t3_validate",
                "agent": "claude",
                "action": "ARCHITECTURE",
                "prompt": "Review the identified risks and suggest 3 passive reconnaissance steps to further analyze the target without alerting defense systems.",
                "depends_on": "t2_interpret"
            })
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

    def execute_agent(self, agent_name, prompt, run_id):
        agent_cfg = next((a for a in self.agents if a["name"] == agent_name), None)
        if not agent_cfg:
            raise ValueError(f"Agent {agent_name} not registered.")

        # Construct CLI call
        full_command = f"{agent_cfg['default_cmd']} \"{prompt}\""
        
        try:
            # Execute via audited wrapper
            output = subprocess.check_output(
                [self.wrapper_path, agent_name, full_command, run_id],
                stderr=subprocess.STDOUT
            ).decode()
            
            metadata = self.extract_metadata(output)
            if not metadata:
                # Fallback: metadata was likely suppressed or agent failed to output it
                return {"error": "Metadata extraction failed", "raw": output}
            return metadata
        except subprocess.CalledProcessError as e:
            return {"error": str(e), "raw": e.output.decode() if e.output else "No output"}

    def run(self, goal):
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        run_path = os.path.join(self.runs_dir, f"{run_id}.json")
        
        print(f"[*] Starting RUN: {run_id}")
        print(f"[*] Goal: {goal}")
        
        tasks = self.decompose_goal(goal)
        run_log = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "goal": goal,
            "tasks": []
        }
        
        context_buffer = ""
        for task in tasks:
            print(f"[>] Executing Task: {task['id']} ({task['agent']})")
            
            if "target" in task and not self.is_authorized(task["target"]):
                print(f"[!] REJECTED: Target {task['target']} is not in scope.")
                task["status"] = "REJECTED_BY_POLICY"
                continue

            current_prompt = task["prompt"] + context_buffer
            result = self.execute_agent(task["agent"], current_prompt, run_id)
            
            # Update context buffer from stdout for following tasks
            if "stdout_path" in result and os.path.exists(result["stdout_path"]):
                with open(result["stdout_path"], "r") as f:
                    context_buffer = f"\n--- PRIOR OUTPUT ({task['id']}) ---\n" + f.read()

            run_log["tasks"].append({
                "task_id": task["id"],
                "agent": task["agent"],
                "metadata": result,
                "timestamp": datetime.now().isoformat()
            })
            
            if result.get("exit_code") != 0:
                print(f"[!] Warning: Task {task['id']} failed with code {result.get('exit_code')}")

        # Save run record
        with open(run_path, "w") as f:
            json.dump(run_log, f, indent=2)
            
        print(f"[*] Run Complete. Metadata: {run_path}")
        return run_log

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 orchestrator.py '<goal>'")
    else:
        orchestrator = MultiLLMOrchestrator()
        orchestrator.run(sys.argv[1])
