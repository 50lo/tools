
## Decision Policy

Treat decision policy as a required part of the workflow, not optional background reading.

Required at task start:

1. List open questions first. If there are none, say that explicitly.
2. Read `agent_rules.yml`.
3. Apply the first applicable rule by priority. Higher-priority rules win.
4. If no rule applies, scan only the relevant entries in `decisions_log.yml`.
5. If there is still no answer, use judgement aligned with project goals, current task, and repo conventions.

Required before final response:

1. Reflect on whether you made a material decision.
2. If yes, append an entry to `decisions_log.yml` before finishing.

Material decisions include:

- product behavior choices that were not fully specified
- process or workflow choices future agents should repeat
- architecture choices or deviations from repo conventions
- assumptions that affect user-visible behavior
- explicit user decisions likely to matter again

Do not log tiny local implementation details, obvious reuse of existing patterns, or choices fully dictated by tests, issues, or existing docs.

Keep both files easy to scan. Read only the relevant parts when possible. `yq` may be used for targeted lookups, but the files should remain understandable from a quick plain-text read.
