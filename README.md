# llm-wiki-skill

A Claude Code skill that builds and maintains a personal LLM wiki — implementing [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Three-layer architecture:

- **`raw/`** — immutable source materials (URLs, papers, files, project graphify exports)
- **`wiki/`** — LLM-curated markdown (concepts, entities, source summaries, comparisons, decisions, notes)
- **`CLAUDE.md`** — the vault's schema and rules (turns the agent into a wiki maintainer)

Unlike [graphify](https://github.com/safishamsi/graphify) (a one-shot per-project code graph), this vault **accumulates many sources over time and is curated conversationally** — it's a compounding artifact, not a single-pass analysis.

## Install

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/dbsdud/llm-wiki-skill.git ~/.claude/skills/wiki
```

Add a pointer in your global `~/.claude/CLAUDE.md`:

```markdown
# wiki
- **wiki** (`~/.claude/skills/wiki/SKILL.md`) - personal LLM Wiki maintainer. Trigger: `/wiki`
When the user types `/wiki`, invoke the Skill tool with `skill: "wiki"` before doing anything else.
```

## Quickstart

```bash
> /wiki setup                                # scaffold a vault in the current directory
> /wiki ingest https://example.com/blog      # fetch + discuss + summarize
> /wiki ingest ~/projects/myrepo             # graphify + snapshot + summarize
> /wiki note                                 # capture a decision/ADR or note
> /wiki query "what did I learn about X?"     # answer with citations
> /wiki lint                                  # health-check the vault
```

## Subcommands

| Command | What it does |
|---|---|
| `/wiki setup [path]` | Scaffold a vault (default: **current directory**) — dirs + `CLAUDE.md` + `.wiki-vault` marker + special files |
| `/wiki ingest <url\|file\|project>` | Auto-detect source; save to `raw/`; discuss takeaways; synthesize `wiki/sources/` + cross-link pages. `--auto` skips discussion |
| `/wiki note [topic]` | Capture your own knowledge (decision/ADR, meeting note, idea) with **no external source** |
| `/wiki query "<question>"` | Answer from wiki pages with citations; save new synthesis as a page |
| `/wiki lint` | Contradictions, stale/superseded claims, orphans, missing pages/cross-references, frontmatter, broken `sources:` |
| `/wiki overview` | Rewrite `wiki/overview.md` from current state |

Colon forms (`/wiki:setup`, etc.) map to the same subcommands.

## Vault resolution

The vault can live **anywhere** — there is no hardcoded path. Non-`setup` commands resolve the active vault by:

1. `--vault <path>` flag, else
2. `WIKI_VAULT` env var, else
3. walking up from the current directory for a `.wiki-vault` marker, else
4. erroring with a hint to run `/wiki setup`.

This lets you keep multiple vaults and have the active one chosen by where you are.

## Vault structure

```
<vault>/
├── .wiki-vault          # root marker (version, name, created)
├── CLAUDE.md            # schema and rules (source of truth for this vault)
├── raw/                 # immutable
│   ├── articles/  papers/  repos/  data/  images/  assets/
└── wiki/                # LLM-owned synthesis
    ├── index.md         # catalog (one-line summary per page)
    ├── log.md           # append-only activity log
    ├── overview.md      # high-level synthesis
    ├── concepts/  entities/  sources/  comparisons/  decisions/  notes/
```

## Page frontmatter

```yaml
---
title: <Human-readable name>
type: concept | entity | source-summary | comparison | decision | note
sources: []          # paths into raw/ (empty if self-authored)
related: []          # paths to other wiki pages (cross-references — fill liberally)
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
---
```

`decision` pages add `status: proposed | accepted | superseded` (+ optional `supersedes` / `superseded-by`).

## Faithful to Karpathy's pattern

- **Conversational ingest** — the LLM reads the source and *discusses key takeaways with you* before writing (`--auto` to skip).
- **Compounding density** — a single source touches many pages, mostly by *updating existing pages and cross-links*, not by spawning empty stubs.
- **Contradiction flagging** — when a new source conflicts with an existing claim, it's flagged in place and the page is updated.
- **Rich lint** — health-checks for contradictions, superseded claims, orphans, important concepts lacking a page, and missing cross-references — not just mechanical frontmatter checks.
- **Content-oriented index** — every page listed with a one-line summary.

## graphify integration

[graphify](https://github.com/safishamsi/graphify) is the recommended raw-input generator for codebases. **The vault is consumer-only** — graphify runs in each *project*, never in the vault. `/wiki ingest <project>` runs the graphify pipeline in the project, snapshots its output to `raw/repos/<name>/`, and synthesizes `wiki/sources/summary-<name>.md`.

## Absolute rules

- Never edit files under `raw/` — immutable
- Never edit past entries in `wiki/log.md` — append-only
- Never create wiki pages without YAML frontmatter
- Never create wiki pages without registering them in `wiki/index.md`
- **Never run `graphify` inside the vault** — consumer-only

## License

MIT — see [LICENSE](LICENSE).

## Credits

- Pattern: [Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- Skill author: [@dbsdud](https://github.com/dbsdud)
