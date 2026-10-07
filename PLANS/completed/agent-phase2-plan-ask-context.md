# Plan: AI agent, phase 2: plans, questions, context and long chats

**Status:** Completed
**Priority:** P1
**Updated:** 2026-10-07

## Goal

Before multi-step work the agent shows its plan as a checklist and waits for
your go-ahead; you can say what to change instead. When a request is
unclear and a wrong guess would cost, it asks you a question with choices
rather than guessing. Every request starts with what it needs to know about
where you are (the folder, the jobs running, the last thing Max did), and a
long chat stays within the token limit because Max summarises the oldest
turns. Builds on phase 1 (`../completed/agent-phase1-batch-verify-memory.md`).

## Tasks

- [x] `plan` tool: steps shown as a checklist (StepKind.PLAN); the `ask`
      callback approves it, cancels it or returns the changes asked for.
- [x] `ask_user` tool: a question with optional choices through the same
      callback; no callback (scripts) means "choose the safe option and say so".
- [x] Context: `agent/context.py`, a few lines added to each request: the
      folder's files by kind, the queue, the last action.
- [x] Long chats: past `COMPACT_AT_CHARS` the oldest turns become one summary
      (one model call); the last turns stay as they were.
- [x] CLI: the plan and questions in the terminal; `ai chat` saves after
      every request, not only on exit.
- [x] AI page: a plan card in the turn; `QuestionDialog` for questions and
      plans.
- [x] Tests, docs (`docs/commands/ai.md`, README, AGENTS.md, CHANGELOG).

## Decisions

- One `ask` callback answers questions and plans: the CLI, the dashboard and
  tests each supply one function.
- Approving a plan doesn't skip the questions before moving, overwriting or
  deleting: the model could still run something the plan didn't name.
- Context goes at the end of the user's message, not in a second system
  message: Gemini's OpenAI-compatible API takes system text only at the start.
- `KEEP_RECENT_REQUESTS` counts earlier requests: with 2, the third request
  starts summarising only once a fourth arrives.
- The first prompt is about 8,650 characters now; `tests/test_agent.py`
  allows 9,000.
