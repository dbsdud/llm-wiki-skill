# llm-wiki-skill

A Claude Code skill that maintains a personal LLM wiki — implementing [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Three-layer architecture:

- **`raw/`** — immutable source materials (URLs, papers, project graphify exports)
- **`wiki/`** — LLM-curated markdown (concepts, entities, source summaries, comparisons)
- **`CLAUDE.md`** — schema and workflow rules

The skill automates the operations Karpathy described — `ingest`, `query`, `lint`, plus vault bootstrap and [graphify](https://github.com/safishamsi/graphify) integration.

## Install

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/dbsdud/llm-wiki-skill.git ~/.claude/skills/wiki
```

Then add a pointer in your global `~/.claude/CLAUDE.md` so Claude Code knows about it:

```markdown
# wiki
- **wiki** (`~/.claude/skills/wiki/SKILL.md`) - LLM Wiki maintainer for ~/vaults. Trigger: `/wiki`
When the user types `/wiki`, invoke the Skill tool with `skill: "wiki"` before doing anything else.
```

## Quickstart

```bash
cd ~ && claude

> /wiki init                                # bootstrap ~/vaults
> /wiki ingest-url https://example.com/blog # fetch + summarize
> /wiki ingest-project ~/projects/myrepo    # graphify + snapshot + summarize
> /wiki query "what did I learn about X?"   # answer with citations
> /wiki lint                                # check vault integrity
```

## Subcommands

| Command | What it does |
|---|---|
| `/wiki init [path]` | Create vault structure (default `~/vaults`) + `CLAUDE.md` + special files |
| `/wiki ingest-project <project-path> [name]` | Run graphify in the project, rsync output to `raw/repos/`, synthesize `wiki/sources/summary-<name>.md` |
| `/wiki ingest-url <url>` | Fetch URL into `raw/articles/`, then synthesize |
| `/wiki ingest-file <path>` | Copy local file into the right `raw/<kind>/`, then synthesize |
| `/wiki query "<question>"` | Answer using wiki pages; save new synthesis as a page |
| `/wiki lint` | Orphans, frontmatter, broken `sources:` paths, stale pages |
| `/wiki overview` | Rewrite `wiki/overview.md` from current state |

## Vault structure

```
vaults/
├── raw/
│   ├── articles/   # blog posts, news, clippings (YYYY-MM-DD-slug.md)
│   ├── papers/     # PDFs
│   ├── repos/      # graphify exports per project
│   ├── data/       # CSV, JSON
│   ├── images/     # diagrams, screenshots
│   └── assets/     # Obsidian attachments
├── wiki/
│   ├── index.md         # catalog
│   ├── log.md           # append-only activity log
│   ├── overview.md      # high-level synthesis
│   ├── concepts/        # ideas, algorithms, patterns
│   ├── entities/        # people, orgs, products
│   ├── sources/         # per-raw-item summaries (1:1)
│   └── comparisons/     # cross-item comparison pages
└── CLAUDE.md            # schema and rules
```

## Page frontmatter

Every wiki page has YAML frontmatter:

```yaml
---
title: <Human-readable name>
type: concept | entity | source-summary | comparison
sources: []          # paths into raw/
related: []          # paths to other wiki pages
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low
---
```

## graphify integration

[graphify](https://github.com/safishamsi/graphify) is the recommended raw-input generator for codebases.

**The vault is consumer-only.** graphify runs in each *project*, not in the vault. `/wiki ingest-project` orchestrates the pipeline **without requiring an LLM API key** by splitting graphify's responsibilities:

1. `graphify update <project>` in the project — refreshes `graph.json` and clusters; no LLM call.
2. Claude curates community labels to 100% coverage (English by default; falls back to top-node label for singleton communities). This replaces the LLM step that `graphify . --wiki` would otherwise perform.
3. `scripts/rebuild_wiki.py` calls `graphify.wiki.to_wiki()` directly with the curated labels — writes `<project>/graphify-out/wiki/` deterministically.
4. `rsync --delete <project>/graphify-out/wiki/ ~/vaults/raw/repos/<name>/`
5. Claude reads `raw/repos/<name>/` and writes `wiki/sources/summary-<name>.md`
6. Concepts/entities pages created/updated; `index.md` and `log.md` updated

If someone runs the full `graphify .` pipeline externally and overwrites the curated labels, `scripts/recover_labels.py` reconstructs them by voting on community ids via the previous filenames in `raw/repos/<name>/`. See SKILL.md for the full flow.

## Absolute rules

- Never edit files under `raw/` — immutable
- Never edit past entries in `wiki/log.md` — append-only
- Never create wiki pages without YAML frontmatter
- Never create wiki pages without registering them in `wiki/index.md`
- **Never run `graphify` inside the vault** — consumer-only

## Customization

- Vault root defaults to `~/vaults`. Override with the `WIKI_VAULT` env var or `/wiki init <path>`.
- The vault's `CLAUDE.md` is the source of truth for conventions in *that vault* — edit it to extend page types, add per-vault rules, etc.

## Why a wiki, not just RAG

> The wiki is a persistent, compounding artifact.
> — Andrej Karpathy

Instead of re-searching and re-synthesizing on every query, the LLM reads new sources, extracts key information, and integrates findings into existing wiki pages. The synthesis accumulates. Cross-references and contradiction-flagging are LLM strengths; bookkeeping that humans abandon, an LLM happily maintains.

## License

MIT — see [LICENSE](LICENSE).

## Credits

- Pattern: [Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) (gist published 2026-04-03)
- Skill author: [@dbsdud](https://github.com/dbsdud)
