"""The AI agent: a model that does the work by running catalog actions.

See PLANS/active/dashboard-first-ai-agent.md (step 4). `Agent` holds one
conversation; `tools` is what the model sees of the catalog; `scope` limits
the folders it may touch. Nothing here prints or prompts: the CLI and the
dashboard pass a `confirm` callback and show the `Step`s it reports.
"""
