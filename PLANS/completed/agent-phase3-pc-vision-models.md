# Plan: AI agent, phase 3: the computer, images, models and evals

**Status:** Completed
**Priority:** P1
**Updated:** 2026-10-07

## Goal

The agent can answer "how much space is left?", "what's eating my memory?",
"open that report" and "which of these photos are screenshots?". Later, if
the maintainer agrees: a shell for what Max's actions can't do, stopping a
process, a cheaper model for simple steps, and evals that score the agent's
choices. Follows phases 1 and 2 (`../completed/agent-phase1-*.md`,
`../completed/agent-phase2-*.md`).

## Tasks

### 3a: safe, done without asking

- [x] `system_info`: disks with free space, memory, CPU, battery, uptime
      (`agent/pc.py`, psutil).
- [x] `processes`: the biggest memory users, narrowed by name. Read-only.
- [x] `open`: a file or folder inside the allowed folders, or an http(s)
      link, with its default app; programs and scripts refused
      (`pc.RUNNABLE_SUFFIXES`, suffix checked on folders too for `.app`).
- [x] `look_at_image`: one image to the vision model with a question
      (`AIEngine.analyze_image_content`), images up to 20 MB.
- [x] Tests, docs.

### 3b: chosen by the maintainer (2026-10-07)

- [x] A shell tool: off by default (`AGENT_SHELL`), every command shown and
      asked before it runs, never with `shell=True`, inside the allowed
      folders, with a time limit and its output capped.
- [x] Stop a process: asks first, never system processes.
- [x] A cheaper model for summaries (`AI_FAST_MODEL`); prompt caching
      where the provider has it.
- [x] Agent evals: `scripts/agent_eval.py` runs scripted requests against
      the configured model in a temporary folder and scores the tool calls
      (batched or not, plan shown, results checked). Costs API calls.

## Decisions

- The cheaper model takes only the chat summaries: the agent is one
  conversation, and every turn picks tools, which needs the main model.
- Opening needs no question: it changes no file. Running a program does,
  so `open` refuses programs, scripts and shortcuts.
- Prompt caching needs no code: OpenAI and Gemini cache a request's
  unchanging start by themselves, and Max keeps the system prompt and tools
  the same between requests (the context goes at the end of the message).
- The evals found two bugs on their first run: relative paths started in the
  process's folder, and the model repeated identical calls after a dry-run
  answer. Both fixed; a request turning to a second kind of change without a
  plan now gets "call plan first".
- The first prompt is about 10,000 characters (2,500 tokens);
  `tests/test_agent.py` allows 10,500; provider-side caching of that
  unchanging start cuts what it costs per turn.
