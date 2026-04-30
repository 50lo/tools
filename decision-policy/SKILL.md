---
name: decision-policy
description: Initialize and use decision policy. Use when user wants document or enforce project principles, tradeoff rules, decision logs, or help making coding agents decide open implementation details consistently.
---

# Decision Policy

Use this skill to initialize or maintain the simpler decision-policy layer in a software project.

The system has two project files:

- `agent_rules.yml`: rules agents use to resolve underspecified product, process, and technical choices.
- `decisions_log.yml`: append-only log of material decisions.

## When To Use

Use this skill when:

- The user asks to initialize decision policy for a project.
- The user wants coding agents to make fewer unnecessary tradeoff questions.
- The user mentions project rules, decision policy, or decision logs.
- You are making a material implementation choice and the repo has `agent_rules.yml`.
- You need to verify changes in `agent_rules.yml` or `decisions_log.yml`.

## Initialize

1. If `agent_rules.yml` already exists, read it and use it.
2. If `decisions_log.yml` already exists, preserve it. It is append-only.
3. If `agent_rules.yml` is missing, create it from [agent_rules.template.yml](references/agent_rules.template.yml). Copy the file exactly.
4. If `decisions_log.yml` is missing, create it from [decisions_log.template.yml](references/decisions_log.template.yml). Copy the file exactly.
5. Add the short instruction from [AGENTS-snippet.md](references/AGENTS-snippet.md) to the relevant project agent context file. Copy the snippet exactly.
6. Run `scripts/validate.py` after creating or editing the files.

## Use During Coding

Required at task start:

1. List open questions first. If there are none, say that explicitly.
2. Read `agent_rules.yml`.
3. Apply the first applicable rule by priority. Higher-priority rules win.
4. If no rule applies, scan only the relevant entries in `decisions_log.yml`.
5. If there is still no answer, use judgement aligned with project goals, current task, and repo conventions.

Required before final response:

1. Reflect on whether you made a material decision.
2. If yes, append an entry to `decisions_log.yml` before finishing.
3. Run `scripts/validate.py` after editing the files.

Material decisions include:

- product behavior choices that were not fully specified
- process or workflow choices future agents should repeat
- architecture choices or deviations from repo conventions
- assumptions that affect user-visible behavior
- explicit user decisions likely to matter again

Do not log tiny local implementation details, obvious reuse of existing patterns, or choices fully dictated by tests, issues, or existing docs.

## Decision Log Rules

- Append new entries. Do not rewrite history except to mark `status: superseded`.
- Use `actor: user` for explicit user decisions and `actor: agent` for agent decisions.
- Log material product, process, or technical decisions.
- Do not log tiny implementation details or obvious repo-pattern reuse.

## Maintenance

Keep both files easy to scan. Read only the relevant parts when possible. `yq` may be used for targeted lookups, but the files should remain understandable from a quick plain-text read.
