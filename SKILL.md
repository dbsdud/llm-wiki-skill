---
name: wiki
description: |
  Use this skill when the user wants to ingest, compile, query, or maintain their personal LLM-curated knowledge vault at `~/vaults/` (Karpathy "LLM Wiki" pattern: immutable `raw/` sources → curated `wiki/` pages with frontmatter, `overview.md`, and `index.md`).

  Trigger on intents like:
  - Save into vault: dropping a URL, gist, paper, file, meeting note, or recent chat answer for long-term keeping ("vault에 넣어줘", "wiki에 컴파일/정리")
  - Search / recall: finding what the vault has on a topic, navigating concept pages ("wiki에 ___ 있어?", "vault에서 찾아")
  - Maintain: rewriting `overview.md`, linting orphans/stale/frontmatter, refreshing `index.md`
  - Initialize: bootstrapping a new vault
  - Any mention of `~/vaults`, `raw/`, `wiki/sources/`, PKM, zettelkasten, or second-brain tied to a knowledge action

  Does NOT trigger for project READMEs, codebase explanation, or running `graphify` itself (the vault is consumer-only).
trigger: /wiki
---

# /wiki

LLM Wiki maintainer for `~/vaults/`. Implements the Karpathy LLM Wiki pattern:

- **raw/** — immutable source materials
- **wiki/** — LLM-owned curated knowledge (concepts, entities, source summaries, comparisons)
- **CLAUDE.md** — schema and workflow rules

The vault is **consumer-only**. `graphify` is never run inside the vault.
Run `graphify` in each project; this skill brings the output into `raw/repos/` and synthesizes a wiki summary.

Reference: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

## Usage

```
/wiki                                       # show this help
/wiki init [path]                           # create vault structure (default ~/vaults)
/wiki ingest-project <project-path> [name]  # graphify project → raw/repos → wiki/sources
/wiki ingest-url <url>                      # fetch URL into raw/articles, then summarize
/wiki ingest-file <path>                    # copy local file into raw/, then summarize
/wiki query "<question>"                    # answer using wiki, file synthesis back
/wiki lint                                  # check orphans, frontmatter, sources, staleness
/wiki overview                              # rewrite wiki/overview.md from current pages
```

## Bundled resources

Read these only when the relevant subcommand fires — they're heavy and shouldn't bloat every invocation:

- `assets/vault-claude-template.md` — the schema file that `/wiki init` writes into a new vault. Treated as the **canonical source of vault conventions**; reusable as a reference when answering questions about vault structure.
- `scripts/rebuild_wiki.py` — invoked from `/wiki ingest-project` Step 5. Rebuilds `graphify-out/wiki/` from `graph.json` + `.graphify_labels.json` without an LLM API key, by calling `graphify.wiki.to_wiki()` directly.
- `scripts/recover_labels.py` — invoked when an external `graphify .` run has overwritten curated labels. Reads the previous labels from `raw/repos/<name>/` filenames and re-maps them to the new community ids via top-node voting.

## Vault resolution

- Default root: `~/vaults`. Override with `WIKI_VAULT` env var or `init [path]`.
- For every non-`init` command: verify `$VAULT/CLAUDE.md` exists. If not, tell the user to run `/wiki init` first and stop.
- Conventions live in `$VAULT/CLAUDE.md`. Read it before any non-trivial operation — it is the source of truth for page types, frontmatter, and absolute rules. The `assets/vault-claude-template.md` is the template version; the live vault may have extensions (ADR conventions, jj workflow notes, etc.) that take precedence.

## Schema evolution

The vault `CLAUDE.md` is a **living document**, not immutable. `/wiki init` writes it once from the template, but as the vault accumulates operational experience, the schema evolves — new page types, new frontmatter fields, new policies. This is expected; trying to keep the live `CLAUDE.md` identical to the template defeats the purpose of a personal vault.

The vault's own conventions (see `$VAULT/CLAUDE.md`) decide *how* to evolve, but the high-level shape is:

- **Small policy additions** (one or two lines — e.g., new ignore pattern, new field convention) → edit the relevant section in `$VAULT/CLAUDE.md` directly. No ADR needed; the line itself is the decision.
- **Operating invariants** (rules that lint/ingest/retrieval depend on, or that future operators must not violate without thinking) → write an ADR under `$VAULT/wiki/decisions/`, then add a one-line entry in the corresponding `$VAULT/CLAUDE.md` section that links to the ADR. The ADR body holds the reasoning and is immutable; the `CLAUDE.md` line is the operational summary.

The asymmetry matters: ADR bodies are append-only history (so future operators can see *why* a rule exists), while `CLAUDE.md` is the always-fresh operating manual (so they can see *what* the rule is at a glance). Linking the two keeps both honest.

This skill does not enforce the ADR-vs-direct-edit choice — that's a judgment call the vault operator makes. But when an ingest or query produces synthesis that should become a vault-wide rule, prompt the user to consider which form fits, rather than silently editing `CLAUDE.md`.

## What you must do when invoked

If the user invoked `/wiki` or `/wiki -h` with no subcommand, print the Usage block verbatim and stop.

Otherwise, bind:

```bash
VAULT="${WIKI_VAULT:-$HOME/vaults}"
TODAY=$(date +%Y-%m-%d)
SKILL_DIR="$HOME/.claude/skills/wiki"   # location of this skill's scripts/ and assets/
```

`$SKILL_DIR` matches the "Base directory for this skill" reported when the skill is invoked. The Python scripts under `$SKILL_DIR/scripts/` invoke `python3` and expect `graphify` to be importable. Concretely this means: whichever `python3` resolves on the user's PATH must be the one with `graphify` installed. Runtime managers like mise or pyenv handle this automatically via shims; on a system Python or virtualenv setup, ensure `pip install graphify` has been run for that interpreter (or activate the matching venv before invoking the skill).

Then dispatch on the subcommand below.

## Common helpers

**Append a log entry** at the end of each operation (never mid-flight, so a partial failure doesn't leave a misleading entry):

```bash
printf '\n## [%s] %s | %s\n' "$TODAY" "$OP" "$MSG" >> "$VAULT/wiki/log.md"
```

`$OP` is one of `init | sync | ingest | query | lint | synthesis`. Past entries are never edited — log is append-only audit trail.

**Read vault schema before non-init operations:** read `$VAULT/CLAUDE.md`. Its rules override anything embedded in this skill, because the vault may have evolved its own conventions on top of the template.

---

### /wiki init [path]

Bootstrap a fresh LLM Wiki vault. Default path is `~/vaults`; if `[path]` is given, use it.

1. **Verify state** — refuse to overwrite an existing vault:
   ```bash
   TARGET="${1:-$HOME/vaults}"
   if [ -f "$TARGET/CLAUDE.md" ]; then
       echo "$TARGET/CLAUDE.md already exists. Refusing to overwrite."
       echo "Remove it first or pick another path."
       exit 1
   fi
   mkdir -p "$TARGET"
   ```

2. **Create directory structure:**
   ```bash
   mkdir -p "$TARGET"/raw/{articles,papers,repos,data,images,assets}
   mkdir -p "$TARGET"/wiki/{concepts,entities,sources,comparisons}
   ```

3. **Write `$TARGET/CLAUDE.md`** by copying `assets/vault-claude-template.md` from this skill verbatim. Use the Write tool to avoid heredoc backtick escaping. The template is the canonical schema; do not paraphrase it inline here.

4. **Write the three special files** with today's date filled in:

   `$TARGET/wiki/index.md`:
   ```markdown
   ---
   title: Index
   type: index
   created: <TODAY>
   updated: <TODAY>
   ---

   # Wiki Index

   전체 wiki 페이지 카탈로그. 새 페이지를 만들 때 반드시 이 파일에 등록한다.

   ## Special
   - [overview](overview.md) — 지식 베이스 전체 high-level 합성
   - [log](log.md) — append-only 활동 로그

   ## Concepts
   _아직 항목 없음._

   ## Entities
   _아직 항목 없음._

   ## Sources
   _아직 항목 없음._

   ## Comparisons
   _아직 항목 없음._
   ```

   `$TARGET/wiki/log.md`:
   ```markdown
   ---
   title: Activity Log
   type: log
   created: <TODAY>
   updated: <TODAY>
   ---

   # Log

   Append-only. 과거 항목 절대 수정 금지.
   포맷: `## [YYYY-MM-DD] <operation> | <description>`

   ## [<TODAY>] init | vault initialized at <TARGET>
   ```

   `$TARGET/wiki/overview.md`:
   ```markdown
   ---
   title: Overview
   type: overview
   sources: []
   related: []
   created: <TODAY>
   updated: <TODAY>
   confidence: low
   ---

   # Overview

   지식 베이스 전체에 대한 high-level 합성.
   충분한 페이지가 쌓이면 다시 작성한다.

   ## 주요 테마
   _아직 ingest된 자료가 없음._

   ## 미해결 질문
   _TBD._

   ## 큰 그림
   _TBD._
   ```

5. **Suggest Obsidian config** (tell, don't write):
   ```
   Obsidian을 사용한다면 .obsidian/app.json 에 다음을 추가:
     "attachmentFolderPath": "raw/assets"
   ```

6. **Report:**
   ```
   LLM Wiki initialized at <TARGET>.
   Schema: <TARGET>/CLAUDE.md
   Next: /wiki ingest-project <project-path>  또는  /wiki ingest-url <url>
   ```

---

### /wiki ingest-project <project-path> [name]

Pipeline: project graphify → vault raw/repos snapshot → curated wiki summary.

**Args:**
- `<project-path>` — absolute or `~`-relative project directory
- `[name]` — optional. Defaults to `basename "$project-path"`

**Steps:**

1. **Resolve and validate:**
   ```bash
   PROJECT="$(cd "${1/#\~/$HOME}" 2>/dev/null && pwd)" || { echo "project path not found: $1"; exit 1; }
   NAME="${2:-$(basename "$PROJECT")}"
   DEST="$VAULT/raw/repos/$NAME"
   ```

2. **Pre-flight check:** if `$PROJECT/graphify-out/graph.json` is missing, tell the user to run `/graphify .` in the project first, then stop.

3. **Refresh graph (no LLM):**
   ```bash
   (cd "$PROJECT" && graphify update . )
   ```

   `graphify update` does AST-based re-extraction + clustering without calling any LLM. It rewrites `graph.json`, `.graphify_labels.json` (with placeholder labels for new communities), and `manifest.json`.

   **Why not `graphify . --wiki`?** The full pipeline requires an LLM API key, produces non-deterministic labels (each run can name the same conceptual community differently — your previous curation is lost), and tends to leave small communities (~5% of total) as placeholders. Splitting the steps lets Claude take over label curation and guarantees 100% coverage.

4. **Curate labels to 100% coverage.**

   Load `.graphify_labels.json`, identify entries matching `^Community \d+$` (graphify's placeholder pattern), and assign meaningful labels per the policy in `$VAULT/CLAUDE.md` — typically:

   - **size ≥ 3 community** — read the community's top nodes from `graph.json` (filter by `node.community == cid`, sort by graph degree), then write a short **English** label that captures the domain. English keeps token usage low and search vocabulary consistent with the code identifiers in the graph. Use Korean only when the term is a Korean-native domain noun (e.g., `테토디`, `행정구역`, `Coway Dept API`).
   - **size 1-2 community** — these are nearly-singleton groups; curating them adds little signal. Use the top node's `label` field as the community label directly (deterministic, no token cost). Truncate to 60 chars if needed.

   The goal is zero placeholder filenames in the final wiki. Anything labeled `Community_N.md` is a curation gap that hurts retrieval — users browsing `raw/repos/<name>/` see noise instead of domain structure.

   Write the curated labels back to `.graphify_labels.json` (`ensure_ascii=False`).

   **If labels were recently overwritten** (graph mtime newer than your last ingest, `.graphify_labels.json.bak*` exists, English labels appeared where you had Korean), an external `graphify .` ran in the meantime. Recover from the previous filenames before curating:

   ```bash
   python "$SKILL_DIR/scripts/recover_labels.py" "$PROJECT" "$DEST"
   ```

   This reads `$DEST/<safe_filename>.md` files (their stems are the previous labels), extracts "Key Concepts" top nodes, and re-maps via voting in the new graph. Labels whose communities were merged or split surface on stderr — record those in the summary's "Open questions" so the user can decide whether to recreate them.

5. **Rebuild wiki articles (no LLM):**
   ```bash
   python "$SKILL_DIR/scripts/rebuild_wiki.py" "$PROJECT"
   ```

   This calls `graphify.wiki.to_wiki()` directly with the curated labels, writing `$PROJECT/graphify-out/wiki/`. Exit code 1 means placeholder files remain — abort and report which communities were missed.

6. **Snapshot to vault raw layer:**
   ```bash
   mkdir -p "$DEST"
   rsync -a --delete "$PROJECT/graphify-out/wiki/" "$DEST/"
   COMMIT=$(cd "$PROJECT" && git rev-parse --short HEAD 2>/dev/null || echo n/a)
   FILES=$(find "$DEST" -type f -name '*.md' | wc -l | tr -d ' ')
   OP=sync MSG="raw/repos/$NAME ($COMMIT, $FILES files)"
   # log this sync step
   ```

7. **Synthesize `$VAULT/wiki/sources/summary-$NAME.md`:**

   Read `$DEST/index.md` (graphify-generated wiki index) and the top community pages by node count. Write with frontmatter:

   ```yaml
   ---
   title: "Summary: <NAME>"
   type: source-summary
   sources:
     - raw/repos/<NAME>/
   related: []
   created: <TODAY>
   updated: <TODAY>
   confidence: high
   ---
   ```

   Body sections (in order):
   - **TL;DR** — 1-2 sentences. What is this project?
   - **주요 모듈** — list of god nodes / large communities with a one-line purpose each
   - **진입점** — entry-point files or APIs (if identifiable from the graph)
   - **외부 의존성** — key external libs/services
   - **인용 가능한 발췌** — short snippets that capture key claims
   - **Open questions** — ambiguities or gaps (include any labels lost in step 4's recovery)

8. **Create/update concept and entity pages — sparingly.** Add `wiki/concepts/<kebab-case>.md` or `wiki/entities/<kebab-case>.md` only when a concept genuinely appears in multiple sources or is reusable. A page per god node hurts retrieval more than it helps — embedding it in the source summary is usually enough.

9. **Update `wiki/index.md`** — add new pages under their categories. Preserve existing entries.

10. **Append log entry** and **report**:
    ```
    Ingested $NAME.
      raw/repos/$NAME/                ($FILES files synced, commit $COMMIT)
      wiki/sources/summary-$NAME.md   (created/updated)
      wiki/concepts/...               ($NEW_C new, $UPD_C updated)
      wiki/entities/...               ($NEW_E new, $UPD_E updated)
      wiki/index.md                   (updated)
    ```

---

### /wiki ingest-url <url>

1. Use the WebFetch tool to fetch and convert to markdown.
2. Derive slug from URL or title. Filename: `$TODAY-<slug>.md`.
3. Save raw to `$VAULT/raw/articles/$TODAY-<slug>.md` with a "Source:" line near the top.
4. Synthesize `$VAULT/wiki/sources/summary-<slug>.md` — same shape as ingest-project (TL;DR, claims, quotes, open questions). frontmatter `sources: [raw/articles/$TODAY-<slug>.md]`.
5. Create/update concept and entity pages only if genuinely reusable.
6. Update `wiki/index.md`.
7. Append log: `OP=ingest MSG="<url> → summary-<slug>"`

---

### /wiki ingest-file <path>

1. Detect kind by extension:
   - `.pdf` → `raw/papers/`
   - `.md`, `.txt` → `raw/articles/`
   - `.csv`, `.json`, `.tsv` → `raw/data/`
   - `.png`, `.jpg`, `.jpeg`, `.webp`, `.svg` → `raw/images/`
   - other → ask user where it goes
2. `cp "$PATH" "$VAULT/raw/<kind>/$(basename "$PATH")"`. If collision, ask user.
3. Same summarize + concepts/entities + index + log flow as ingest-url.

---

### /wiki query "<question>"

1. Read `$VAULT/wiki/index.md`.
2. Pick 3-5 candidate pages by keyword relevance to the question.
3. Read those pages; follow `related:` and `sources:` as needed.
4. Compose answer **with citations to wiki page paths** (e.g. `wiki/concepts/foo.md`).
5. If the wiki lacks enough material, say so explicitly — hallucinating undermines the vault's value as a trustworthy reference.
6. If your synthesis is genuinely new and reusable (not already in any page), save it:
   - Concept-level → new/updated `wiki/concepts/...md`
   - Cross-page comparison → new `wiki/comparisons/...md`
   - Update `wiki/index.md` to register
7. Append log: `OP=query MSG="<question>"` (truncate question to ~80 chars)

---

### /wiki lint

Run these checks across `$VAULT/wiki/**/*.md` (skip `index.md`, `log.md`, `overview.md`):

1. **Orphans** — pages with zero inbound links from other wiki pages. Use grep to count `[text](path)` and `[[wikilink]]` references.
2. **Frontmatter** — missing required fields: `title`, `type`, `sources`, `created`, `updated`. Type-specific fields too.
3. **Broken sources** — for each page's `sources:` array, verify each path exists relative to `$VAULT`.
4. **Stale** — `updated:` more than 90 days before `$TODAY`.

Report findings as a checklist. Auto-fix only safe items where the intent is unambiguous:
- Missing `updated:` → add with current date
- Missing `confidence:` on non-index pages → add `medium`

Anything else (orphans, broken sources, stale content) is a judgment call — surface to the user.

Append log: `OP=lint MSG="$ORPHANS orphan / $FM frontmatter / $SRC sources / $STALE stale"`

---

### /wiki overview

Rewrite `$VAULT/wiki/overview.md` from current wiki state.

1. Read `wiki/index.md`, then every `wiki/concepts/*.md` and `wiki/entities/*.md`.
2. Identify:
   - **주요 테마** — clusters of related concepts (3-5 themes)
   - **미해결 질문** — collected from "Open questions" sections of source summaries
   - **큰 그림** — what shape is the knowledge taking?
3. Overwrite `wiki/overview.md`:
   ```yaml
   ---
   title: Overview
   type: overview
   sources: []
   related: [<top 5 concept paths>]
   created: <preserve from existing overview>
   updated: <TODAY>
   confidence: medium
   ---
   ```
   Body: 주요 테마 / 미해결 질문 / 큰 그림 sections.
4. Append log: `OP=synthesis MSG="overview rewrite — N themes, M open questions"`

---

## Absolute rules

These are invariants that keep the vault's retrieval value intact. Violating any of them breaks downstream tools or destroys provenance.

- **Don't edit files under `$VAULT/raw/`.** The whole point of the raw layer is immutability — once you start editing, the wiki's "this is what the source actually said" guarantee collapses.
- **Don't edit past entries in `$VAULT/wiki/log.md`.** It's an audit trail; rewriting history makes it useless. Append only.
- **Don't create wiki pages without YAML frontmatter.** lint and retrieval both depend on frontmatter; pages without it are invisible to those tools.
- **Don't create new wiki pages without registering in `$VAULT/wiki/index.md`.** A page no one can find through the index is dead weight.
- **Don't run `graphify` inside the vault.** The vault is consumer-only; running graphify here would rewrite raw/ snapshots and break the ingest contract.
- **Don't leave placeholder labels after `/wiki ingest-project`.** `Community_NN.md` / `Cluster_NN.md` filenames are noise in retrieval and indicate the curation step was skipped.
- **For non-init commands, if `$VAULT/CLAUDE.md` is missing, stop and ask the user to run `/wiki init` first.** Operating without the schema means making up conventions that won't match the rest of the vault.

## Honesty rules

- If a source summary doesn't have enough material for a section, write `_TBD_` — fabrication is worse than absence.
- Mark `confidence: low` when synthesis is speculative. The frontmatter is how downstream queries decide how much to trust a page.
