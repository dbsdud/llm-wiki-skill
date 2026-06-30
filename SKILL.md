---
name: wiki
description: |
  Use this skill for any action on the user's **personal knowledge vault** — a long-lived, LLM-curated store they call a wiki, vault, second brain, knowledge base, 지식베이스, PKM, or zettelkasten. It follows Andrej Karpathy's "LLM Wiki" pattern (immutable `raw/` sources → curated `wiki/` pages with frontmatter, an `index.md` catalog, an append-only `log.md`, a synthesized `overview.md`). This is the user's own accumulated notes-and-sources collection, **NOT the current codebase**. Trigger eagerly even when "wiki" is never said, whenever they want to:
  - **Stash a source to keep**: drop a URL, article, paper, PDF, file, or graphify output into the vault so they don't forget it ("이거 정리해둬", "vault에 넣어줘", "나중에 까먹을 것 같아")
  - **Recall**: search what they've already saved on a topic ("내 knowledge base에서 ___ 찾아", "내가 X에 대해 뭘 알고 있지")
  - **Bootstrap**: scaffold a new vault in the current directory or a chosen path ("wiki 만들어줘", "여기에 지식베이스 셋업", "/wiki:setup")
  - **Author**: capture their own notes, ideas, or a design decision / ADR; merge sources into a summary page ("결정 기록해줘", "ADR 남겨")
  - **Maintain**: hunt orphans, contradictions, stale claims, missing pages/cross-references (lint); rewrite the overview

  Colon forms (`/wiki:setup`, `/wiki:ingest`, …) map to the same subcommands.

  Do NOT trigger for: explaining or graphing the current codebase, project READMEs, generic PKM/tool-recommendation questions, or running `graphify` itself (the vault is consumer-only — it ingests graphify output but never runs it).
trigger: /wiki
---

# /wiki

개인 **LLM Wiki** maintainer. Karpathy의 LLM Wiki 패턴을 구현한다.
참조: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

3-layer 아키텍처:
- **raw/** — immutable 원본 (URL·논문·파일·graphify export). 읽기만, 수정 안 함.
- **wiki/** — LLM이 소유한 합성 (개념·인물·소스요약·비교·결정·overview).
- **vault의 CLAUDE.md** — 그 vault의 스키마·규칙. 에이전트를 maintainer로 바꾼다.

핵심: 위키는 **누적되는 영속 산출물**이다. 질의마다 raw를 재합성하지 않고, 한 번 컴파일해 통합한 뒤 최신 상태로 유지한다. graphify(프로젝트 1회성 코드 그래프)와 달리, 이 vault는 여러 소스를 오래 누적하며 **대화형으로** 큐레이션한다.

vault는 **consumer-only**다 — graphify 산출물을 들이되, vault 안에서 graphify를 실행하지 않는다.

## Usage

```
/wiki                              # 이 도움말
/wiki setup [path]                 # vault 스캐폴딩 (default: 현재 디렉토리)
/wiki ingest <url|file|project>    # 외부 소스 → raw/ → wiki 합성 (대화형, --auto로 비대화)
/wiki note [topic]                 # 외부 소스 없이 본인 지식(결정·메모) 직접 캡처
/wiki query "<question>"           # wiki로 답변(인용), 새 합성은 페이지로 저장
/wiki lint                         # health-check (모순·낡은주장·orphan·누락개념/교차참조)
/wiki overview                     # overview.md 재합성
```

콜론 표기(`/wiki:setup` 등)도 같은 서브커맨드로 받는다.

## Vault 해석

`setup`을 제외한 모든 명령은 작업 대상 vault를 다음 우선순위로 찾는다:

1. `--vault <path>` 플래그가 있으면 그 경로
2. `WIKI_VAULT` 환경변수가 있으면 그 경로
3. 없으면 **현재 디렉토리에서 상위로 올라가며** `.wiki-vault` 마커를 찾는다 (가장 가까운 것이 활성 vault)
4. 그래도 없으면 중단하고 안내: `vault를 찾지 못했습니다. /wiki setup [path]로 먼저 만들거나 WIKI_VAULT를 설정하세요.`

해석 후 `$VAULT/CLAUDE.md`(스키마)를 **반드시 먼저 읽는다**. 그 vault의 CLAUDE.md가 관례의 source of truth이며, 충돌 시 이 스킬보다 우선한다.

## 호출 시 행동

인자 없이 `/wiki`(또는 `/wiki -h`) → Usage 블록을 그대로 출력하고 멈춘다.

그 외에는 바인딩:

```bash
SKILL_DIR="${WIKI_SKILL_DIR:-$HOME/.claude/skills/wiki}"
TODAY=$(date +%Y-%m-%d)
```

`setup`이면 아래 setup 절로, 그 외에는 Vault 해석 후 해당 서브커맨드로 디스패치한다.

## 공통 헬퍼

**로그 append** (작업 끝에만, 중간 금지):
```bash
printf '\n## [%s] %s | %s\n' "$TODAY" "$OP" "$MSG" >> "$VAULT/wiki/log.md"
```
`$OP` ∈ `setup | ingest | note | query | lint | synthesis`. **기존 로그 라인 절대 수정 금지 — append-only.**

---

## /wiki setup [path]

현재 디렉토리(인자 없으면) 또는 지정 경로에 새 LLM Wiki vault를 스캐폴딩한다.

1. **타깃 결정 & 충돌 검사:**
   ```bash
   TARGET="$(cd "${1:-.}" 2>/dev/null && pwd)" || { echo "path not found: $1"; exit 1; }
   if [ -e "$TARGET/.wiki-vault" ] || [ -e "$TARGET/CLAUDE.md" ]; then
       echo "$TARGET 에 이미 vault(또는 CLAUDE.md)가 있습니다. 덮어쓰지 않습니다."; exit 1
   fi
   ```

2. **디렉토리 생성:**
   ```bash
   mkdir -p "$TARGET"/raw/{articles,papers,repos,data,images,assets}
   mkdir -p "$TARGET"/wiki/{concepts,entities,sources,comparisons,decisions,notes}
   ```

3. **마커 & 스키마 작성** (템플릿 복사 후 placeholder 치환 — 템플릿에 backtick이 많아 heredoc 대신 cp+sed):
   ```bash
   NAME="$(basename "$TARGET")"
   printf '{"version":1,"name":"%s","created":"%s"}\n' "$NAME" "$TODAY" > "$TARGET/.wiki-vault"

   cp "$SKILL_DIR/assets/vault-CLAUDE.md.template" "$TARGET/CLAUDE.md"
   for f in index log overview; do
       cp "$SKILL_DIR/assets/$f.md.template" "$TARGET/wiki/$f.md"
   done
   # placeholder 치환 (BSD sed)
   sed -i '' "s/{{DATE}}/$TODAY/g" "$TARGET/CLAUDE.md" "$TARGET/wiki/"{index,log,overview}.md
   sed -i '' "s|{{TARGET}}|$TARGET|g" "$TARGET/CLAUDE.md" "$TARGET/wiki/log.md"
   ```

4. **선택: 버전관리.** vault를 git/jj로 추적하면 변경 이력이 남는다. 사용자에게 물어보고 원하면:
   ```bash
   (cd "$TARGET" && git init -q && git add -A && git commit -qm "chore: LLM wiki vault 초기화")
   ```
   (jj 사용자라면 `jj git init --colocate` 후 describe.) 강요하지 않는다.

5. **Obsidian 힌트** (작성하지 말고 안내만): `Obsidian을 쓴다면 .obsidian/app.json 의 attachmentFolderPath 를 "raw/assets" 로.`

6. **보고:**
   ```
   LLM Wiki initialized at <TARGET>.
   Schema: <TARGET>/CLAUDE.md
   Next: /wiki ingest <url|file|project>  또는  /wiki note
   팁: 이 vault 밖에서 쓰려면 WIKI_VAULT=<TARGET> 설정.
   ```

---

## /wiki ingest <url|file|project>

외부 소스를 raw/로 들이고 wiki로 합성한다. **대화형이 기본** — Karpathy의 "key takeaway를 사용자와 논의" 단계를 포함한다. `--auto` 플래그면 논의를 생략하고 합리적 판단으로 진행한다.

### 소스 타입 자동 감지
- `http://` / `https://`로 시작 → **URL**
- 존재하는 디렉토리 → **project** (graphify 파이프라인)
- 존재하는 파일 → **file** (확장자로 분류)
- 그 외 → 사용자에게 무엇인지 질의

### A. URL
1. WebFetch로 가져와 마크다운 변환.
2. URL/제목에서 slug 도출. `raw/articles/$TODAY-<slug>.md`로 저장 (상단에 `Source: <url>` 줄).

### B. file
확장자로 분류 후 복사 (충돌 시 사용자에게 질의):
- `.pdf` → `raw/papers/` · `.md`/`.txt` → `raw/articles/` · `.csv`/`.json`/`.tsv` → `raw/data/`
- `.png`/`.jpg`/`.jpeg`/`.webp`/`.svg` → `raw/images/` · 그 외 → 어디 둘지 질의

### C. project
`references/graphify-ingest.md`를 읽고 그 파이프라인을 따른다 (graph 갱신 → community 라벨 검증 → wiki export → `raw/repos/` 스냅샷). vault 안에서 graphify를 실행하지 않는다 (소스는 항상 프로젝트).

### 합성 (A·B 공통, C는 graphify-ingest.md가 담당)
1. **(대화형, --auto가 아니면)** 소스를 읽고 핵심 takeaway 3~5개를 사용자에게 제시 → 강조점·저장 범위를 조율한다.
2. `wiki/sources/summary-<slug>.md` 작성. frontmatter `type: source-summary`, `sources: [raw/.../<file>]`. 본문: TL;DR / 핵심 주장 / 인용 발췌 / Open questions.
3. **concept·entity 갱신 (교차참조 우선)** — vault CLAUDE.md "교차참조 & 페이지 밀도" 규칙을 따른다. 기존 페이지의 `related:`·본문 링크를 적극 갱신하고, 여러 소스에 재사용될 개념만 신규 페이지로. 한 소스가 여러 페이지를 건드리는 게 정상이다.
4. **모순 플래깅** — 새 소스가 기존 주장과 충돌하면 vault CLAUDE.md "모순 플래깅" 절차로 표시·갱신.
5. `wiki/index.md`에 신규 페이지를 `[제목](경로) — 한 줄 요약`으로 등록.
6. 로그: `OP=ingest MSG="<source> → summary-<slug> (+N concepts, +M entities)"`

---

## /wiki note [topic]

외부 raw 소스 **없이** 본인이 저작하는 지식을 직접 캡처한다 (설계 결정/ADR, 가끔의 회의노트, 아이디어). 대화형으로 내용을 끌어낸다.

1. `topic`이 없으면 무엇을 기록할지 묻는다. 성격을 판별:
   - 설계·아키텍처 **결정** → `wiki/decisions/<NNNN>-<kebab>.md`, `type: decision`, `status: proposed|accepted`. 본문: 맥락 / 결정 / 근거 / 결과. 번호는 기존 최대+1.
   - 재사용 가능한 **개념** → `wiki/concepts/`.
   - 자유 메모·회의 → `wiki/notes/<TODAY>-<kebab>.md`, `type: note`.
2. frontmatter `sources: []` (self-authored), `related:`는 닿는 기존 페이지로 채운다.
3. `wiki/index.md` 등록.
4. 로그: `OP=note MSG="<title> → <path>"`

---

## /wiki query "<question>"

1. `wiki/index.md`를 읽고 키워드 관련성으로 후보 페이지 3~5개 선택.
2. 그 페이지들을 읽고, 필요하면 `related:`·`sources:`를 따라간다.
3. **wiki 페이지 경로를 인용**해 답한다 (예: `wiki/concepts/foo.md`).
4. 재료가 부족하면 **명시적으로** 부족하다고 말한다 — 지어내지 않는다.
5. 합성이 진정 새롭고 재사용 가능하면 페이지로 저장:
   - 개념 수준 → `wiki/concepts/` 신규/갱신
   - 교차 비교 → `wiki/comparisons/` 신규
   - `wiki/index.md` 등록.
6. 로그: `OP=query MSG="<question>"` (질문은 ~80자로 절단).

---

## /wiki lint

`references/lint.md`를 읽고 그 체크리스트를 수행한다. Karpathy의 health-check를 충실히 구현:
페이지 간 **모순**, **superseded(낡은) 주장**, **orphan**, **페이지 없는 중요 개념**, **누락 교차참조**, 데이터 갭 + 기계적 검사(frontmatter, broken sources, stale 날짜).

안전한 항목만 자동수정하고, 나머지(모순 해소·페이지 생성/삭제·교차참조 추가)는 사용자에게 제안·승인받는다.

---

## /wiki overview

`$VAULT/wiki/overview.md`를 현재 상태에서 재합성한다.

1. `wiki/index.md`, 이어서 모든 `concepts/*.md`·`entities/*.md`를 읽는다.
2. 식별: **주요 테마**(관련 개념 군집 3~5) / **미해결 질문**(source-summary들의 Open questions) / **큰 그림**.
3. `overview.md`를 덮어쓴다 (frontmatter `created:`는 기존 보존, `updated:`는 오늘, `related:`는 상위 5개 개념 경로).
4. 로그: `OP=synthesis MSG="overview rewrite — N themes, M open questions"`

---

## 절대 규칙

- `$VAULT/raw/` 수정 금지 (immutable)
- `$VAULT/wiki/log.md` 과거 항목 수정 금지 (append-only)
- frontmatter 없는 wiki 페이지 생성 금지
- `$VAULT/wiki/index.md`에 등록하지 않고 새 페이지 생성 금지
- **vault 안에서 graphify 직접 실행 금지** (consumer-only — 소스는 항상 프로젝트)
- 작업 전 `$VAULT/CLAUDE.md`를 읽고, 충돌 시 그것을 우선한다

## 정직성 규칙

- 섹션 재료가 부족하면 `_TBD_` — 지어내지 않는다
- 합성이 사변적이면 `confidence: low`
- 답변에 source 경로를 인용 — provenance 없는 합성 금지
- 교차참조에는 적극적, 신규 페이지 생성에는 신중 (밀도는 링크에서 온다)
