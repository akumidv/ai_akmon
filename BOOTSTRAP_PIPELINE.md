# BOOTSTRAP_PIPELINE

One-time deployment pipeline for initial setup and rollout.
Run this checklist only once per parent project integration.

1. Integration baseline
	- Add the repository as a submodule at _dev/ai_governance in the parent project.
	- Confirm submodule path is exactly _dev/ai_governance.
	- Ensure parent-project root layer exists: AGENTS.md and folders skills/, tools/, memory/ (create if missing, keep and update if existing).
	- Ensure parent-project dev layer exists: _dev/TASKS.md, _dev/skills/, _dev/tools/, _dev/memory/ (create if missing, keep and update if existing).
	- Example idempotent bootstrap command from parent-project root: mkdir -p skills tools memory _dev/skills _dev/tools _dev/memory && [ -f AGENTS.md ] || touch AGENTS.md && [ -f _dev/TASKS.md ] || touch _dev/TASKS.md
	- If files already exist, do not overwrite; apply only required updates aligned with current project state.
	- Create or update root AGENTS.md in the parent project using requirements from _dev/ai_governance.
	- Verify that a developer and contributors (fork/commit workflow) can clone and init submodules in one documented flow.
	- Add a short parent-project note describing why this submodule exists.

2. Operational contract
	- Define expected inputs from the parent project to this submodule.
	- Define expected outputs (artifacts, notes, helper commands, checklists).
	- Confirm ownership: who updates skills, tools, and memory.

3. Skills bootstrap
	- Add the first project-specific skill in root skills/.
	- Add the first development-workflow skill in _dev/skills/.
	- Include goal, preconditions, ordered steps, and verification checklist.
	- Validate that the skill is runnable as-is in a clean checkout with submodule mounted at _dev/ai_governance.

4. Tools bootstrap
	- Add one deterministic helper in root tools/ for a repeated operation.
	- Add one deterministic development helper in _dev/tools/.
	- Document execution command and required environment next to the tool.
	- Add a simple success/failure verification step.

5. Quality guardrails
	- Add minimal lint/test command checklist used before updates.
	- Define a small acceptance checklist for any change in this submodule.

6. Memory bootstrap
	- Record the first stable integration decision in root memory/.
	- Record the first stable development-workflow decision in _dev/memory/.
	- Keep one file per decision with concise operational wording.
