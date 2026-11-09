---
name: example-agent
description: One line - what this agent does and when the orchestrator calls it. No "use proactively", no "must be used".
tools: Read, Grep, Glob, Bash
disallowedTools: Agent, Skill, mcp__*
omitClaudeMd: true
maxTurns: 40
model: sonnet
effort: medium
# skills: [skill-name]   # only skills this agent cannot work without; their full text is preloaded
---

<!--
TEMPLATE — copy to agents/<name>.md, delete every comment.
The payload injects core/subagent-contract.md right after the frontmatter,
so do NOT repeat here: reporting format, language rules, "do not invent facts".

Size: aim for 120–250 lines. Over 300 lines means a skill is hiding inside the agent — move the reference part out.
Description: neutral. The orchestrator decides who runs. Words like "proactively" make Claude Code auto-invoke.
Tools: smallest set. Reviewers: Read, Grep, Glob, Bash. Writers: add Edit, Write.
model/effort here are defaults; agent-models.json pins the real values at build time.
-->

# <Agent name>

## Role

<!-- 2–4 sentences: what it is responsible for and what it is NOT responsible for. -->

## Inputs

<!-- What the orchestrator's brief always contains for this agent. If something is missing, the agent asks back instead of guessing. -->

- Task id and goal
- Files it may write: <list or "none">
- Docs anchors to read: `docs/<FILE>.md#<anchor>`
- <role-specific input>

## Workflow

<!-- Numbered steps. Each step is one action with an observable result. -->

1. <step>
2. <step>
3. <step>

## Must

<!-- Hard rules for this role. Each rule that concerns code has an id and an example below. -->

- R-<AREA>-<NAME>: <rule in one line>

## Must not

- <thing this agent never does, e.g. edit files outside its write set>

## Examples

### R-<AREA>-<NAME> — <short title>

Bad:
```python
# code that breaks the rule
```
Why: <one line: what goes wrong in production>

Good:
```python
# the same task done right
```

## Output

<!-- Exact shape of the final message back to the orchestrator. Keep it parseable. -->

```text
STATUS: done | blocked | needs-decision
FILES: <changed files or "none">
CHECKS: <command> → <numbers>
FINDINGS:
- [<severity>] <rule id> <file>:<line> — <one line> → <fix>
NOTES: <decisions taken alone, what is not done>
```
