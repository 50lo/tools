---
name: decision-policy
description: Initialize and use decision policy. Use when user wants document or enforce project principles, tradeoff rules, decision logs, or help making coding agents decide open implementation details consistently.
---

# Decision Policy

Use this skill to initialize or maintain a lightweight decision-policy layer in a software project.

The system has two project files:

- `agent_principles.yml`: user-authored ranked priorities for open implementation choices.
- `decisions_log.yml`: append-only log of material tradeoff decisions.

This is not a substitute for tests, CI, security review, permission checks, or approval gates. Decision policy only chooses among acceptable implementation options.

## When To Use

Use this skill when:

- The user asks to initialize decision policy for a project.
- The user wants coding agents to make fewer unnecessary tradeoff questions.
- The user mentions ranked principles, razors, sieves, project priorities, or decision logs.
- You are making a material implementation choice and the repo has `agent_principles.yml`.
- You need to verify changes in `agent_principles.yml` or `decisions_log.yml` fisle.

## Initialize

1. If `agent_principles.yml` already exists, read it and use it.
2. If `decisions_log.yml` already exists, preserve it. It is append-only.
3. If both `agent_principles.yml` and `decisions_log.yml` abesent,iInspect the project root for existing agent context files: `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.agents/skills/`, or similar and try to derive principles from these files.
4. Ask the user a small number of priority questions:
   - What is this project optimizing for first: delivery speed, user convenience, reliability, maintainability, cost, polish, or something else?
   - When product or implementation details are underspecified, what should the agent usually prefer?
   - Should existing repo conventions override these principles when they conflict?
   - Are there any project-level boundaries where the agent should not decide autonomously because no general principle can safely resolve the choice?
5. Draft `agent_principles.yml` from the user's answers. Use [agent_principles.template.yml](references/agent_principles.template.yml) as the starting shape.
6. Create `decisions_log.yml` if missing. Use [decisions_log.template.yml](references/decisions_log.template.yml).
7. Add the short instruction from [AGENTS-snippet.md](references/AGENTS-snippet.md) to the relevant project agent context file. If the repo uses multiple agent context files, prefer the file that the user's active agent reads. If unsure, ask.
8. Stop and ask the user to approve the initial principles before treating them as active.

## Use During Coding

Before starting any work - task implementation, fixing bug, etc.

1. Identify open questions and their tradeoffs.
2. Read `agent_principles.yml`.
3. Go through sieves one by one in the rank order and use the first applicable sieve to resolve your question. Skip the rest of sieves - the first applicable sieve always wins.
4. If you there is no sieve applicable to your open question, search `decisions_log.yml` for relevant decisions made in the past and rationale used to justify those decisions. Try to make decision basing on what you found.
5. If there is no relevant principles or previous decision, use your judgement and do you best to make decision aligned with project goals, requirements, planned work.
6. Log only material decisions in `decisions_log.yml`. Run script validation script `scripts/validate.py` distributed with this skill.

Material decisions include:

- assumptions that affect user-observable behavior.
- architecture choices.
- deviations from existing repo conventions.
- choices future agents are likely to revisit.
- decisions explicitly made by the user in conversation and likely to be useful in the future.

Do not log tiny local implementation details, obvious repo-pattern reuse, or decisions fully determined by a PRD / issue / test / project documentation.

## Decision Log Rules

- Append new entries. Do not rewrite old entries except to mark `status: superseded`.
- Use `actor: user` for explicit user decisions; use `actor: agent` for agent decisions.
- Use one of these `basis` values:
  - `explicit_user_instruction`
  - `derived_from_principles`
  - `repo_pattern`
  - `agent_judgment`
- Prefer `derived_from_principles` over `agent_judgment` when a principle clearly resolves the choice.
- Preserve old entries as receipts. Do not delete low-trust or superseded decisions.

## Maintenance

If the log becomes noisy, propose a manual lint:

- mark stale decisions as `superseded`.
- flag contradictions between decisions and current principles.
- propose to promote repeated decisions into candidate principles only after the pattern is obvious.
