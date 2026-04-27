## Decision Policy

When you start working on a task, list all open questions first. To answer open questions read `agent_principles.yml` and apply decision principles according to the ranked priorities. If there is no appicable principles, look at previous decisions in `decisions_log.yml` and try to derive answer from those decisions. 

Decide autonomously by deriving answers from the principles and precedence rules. If there is no relevant principles or previous decision, use your judgement and do you best to make decision aligned with project goals, requirements, planned work.

Update decisions log when you make important decisions that can be useful for future agent sessions. Log only material tradeoff decisions in `decisions_log.yml`: assumptions, user-visible behavior, architecture choices, deviations from repo conventions, and choices future agents may otherwise revisit.
