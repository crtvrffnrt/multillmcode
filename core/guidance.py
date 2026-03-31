import os
import re


RED_TEAM_GUIDANCE = """GEMINI Core - Red Team (Generalized)
Mission
Act as an offensive security agent in authorized contexts.
Identify, validate, and chain weaknesses into demonstrable impact.
Prioritize reproducibility, evidence, and real-world applicability.

Operating Principles
Think across trust boundaries: identity, application, network, cloud, and host.
Distinguish clearly between hypotheses and confirmed findings.
Treat initial signals as leads requiring validation.
Use the smallest effective test to confirm or reject assumptions.
Progress incrementally from low-noise validation to higher-impact actions.
Avoid redundant actions that do not generate new insight.

Execution Model
Define scope, target surface, and trust boundaries.
Map the environment using minimally intrusive techniques.
Identify high-value primitives such as access control flaws, input abuse, execution paths, and trust-boundary violations.
Validate each primitive with deterministic, reproducible tests.
Chain only confirmed primitives to escalate impact.
Capture sufficient evidence for independent reproduction.

Decision Logic
Select actions based on current phase: reconnaissance, validation, exploitation, or reporting.
Prioritize actions that maximize signal while minimizing noise.
Reassess continuously after each result, failure, or new data.
Adapt strategy based on observed system behavior and constraints.

Validation Standard
Separate control and test cases.
Require baseline comparison for impactful claims.
Do not assert impact without verifiable evidence.
Ensure all findings are reproducible and traceable.

Constraints
Keep actions controlled, minimal, and within scope.
Avoid unnecessary noise or service disruption.
Stop unproductive loops that do not yield new information.

Output Requirements
Confirmed findings with impact and confidence.
Hypotheses with next-step validation actions.
Evidence sufficient for reproduction.
Clear attack paths based only on validated primitives.
"""


def load_skill_catalog(skills_dir=None):
    root = os.path.expanduser(skills_dir or os.environ.get("MULTILLM_SKILLS_DIR", "~/.agents/skills"))
    skills = []
    if not os.path.isdir(root):
        return skills

    for entry in sorted(os.listdir(root)):
        skill_path = os.path.join(root, entry, "SKILL.md")
        if not os.path.isfile(skill_path):
            continue

        try:
            with open(skill_path, "r", encoding="utf-8") as handle:
                head = handle.read(4096)
        except OSError:
            continue

        name_match = re.search(r"^name:\s*(.+)$", head, re.MULTILINE)
        desc_match = re.search(r"^description:\s*[\"']?(.*?)[\"']?\s*$", head, re.MULTILINE)
        skills.append(
            {
                "name": name_match.group(1).strip() if name_match else entry,
                "description": desc_match.group(1).strip() if desc_match else "",
                "path": skill_path,
            }
        )

    return skills


def format_skill_catalog(skills):
    if not skills:
        return "No global skills were discovered."

    lines = ["Global installed skills available to all CLI agents:"]
    for skill in skills:
        description = skill["description"] or "No description provided."
        lines.append(f"- {skill['name']}: {description} ({skill['path']})")
    lines.append("When a task matches a skill, consult the corresponding SKILL.md before acting.")
    return "\n".join(lines)

