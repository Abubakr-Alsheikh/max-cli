# Third-party skills

These skills are vendored copies of upstream skills. Each one was read in full before it was added. Every modified `SKILL.md` starts with a **Project overrides (Max CLI)** block, and that block wins over the upstream text. To update a skill, diff it against the upstream commit listed here and keep the override block.

| Skill | Upstream | Commit | License | Local changes |
|---|---|---|---|---|
| systematic-debugging | [obra/superpowers](https://github.com/obra/superpowers) `skills/systematic-debugging` | `5bf4e78` | MIT | Override block. Dropped the test-pressure files, CREATION-LOG, the `.ts` example and `find-polluter.sh` |
| test-driven-development | obra/superpowers `skills/test-driven-development` | `5bf4e78` | MIT | Override block |
| verification-before-completion | obra/superpowers `skills/verification-before-completion` | `5bf4e78` | MIT | Override block |
| python-testing-patterns | [wshobson/agents](https://github.com/wshobson/agents) `plugins/python-development/skills/python-testing-patterns` | `4236bb9` | MIT | Override block |
| python-type-safety | wshobson/agents `.../python-type-safety` | `4236bb9` | MIT | Override block |
| python-error-handling | wshobson/agents `.../python-error-handling` | `4236bb9` | MIT | Override block |
| ruff | [astral-sh/claude-code-plugins](https://github.com/astral-sh/claude-code-plugins) `plugins/astral/skills/ruff` | `f3ce88a` | MIT (dual MIT/Apache-2.0) | Override block |
| sharp-edges | [trailofbits/skills](https://github.com/trailofbits/skills) `plugins/sharp-edges/skills/sharp-edges` | `32e34f8` | CC BY-SA 4.0 (modified copy under the same license) | Override block. Only the Python and config references kept, and the reference table trimmed |
| textual-builder | smithery.ai `textual-builder` (also in `.agents/skills/`, see `skills-lock.json`) | hash `8c9a99e0` | as distributed | Override block. New description. Added `references/workers-and-testing.md` (verified on Textual 8.2.7). Template made Python 3.9-safe. Install and version lines corrected |

## Rejected after review
- **wshobson python-packaging:** generic, and the project is already packaged.
- **wshobson uv-package-manager:** recommends `curl | sh`, and the project uses pip.
- **aperepel/textual-tui-skill:** about ten APIs broken on Textual 8.x (`App.dark`, invalid TCSS, wrong worker usage).
- **trailofbits modern-python:** installs PATH shims that push uv, ty and Python 3.11+.
- **trailofbits supply-chain-risk-auditor:** bundles about 200KB of network-calling scripts. Install it as a plugin only when you need it.
- **Official security-guidance plugin:** adds an LLM review on every stop, commit and push, and its checks target web apps.
- **Astral plugin as a whole:** it starts an unpinned `uvx ty@latest` LSP server, so only the ruff skill was taken.
