# Project ingest — graphify pipeline

`/wiki ingest <project-path>`로 코드베이스를 들일 때의 상세 절차.
SKILL.md의 ingest 디스패치에서 소스가 *디렉토리(프로젝트)*로 판정되면 여기로 온다.

파이프라인: **프로젝트에서 graphify 실행 → vault `raw/repos/` 스냅샷 → `wiki/sources/` 합성**.

> vault는 consumer-only다. graphify는 항상 *프로젝트* 안에서 돈다. vault 안에서 실행하지 않는다.

## 1. 경로 해석 & 검증

```bash
PROJECT="$(cd "${1/#\~/$HOME}" 2>/dev/null && pwd)" || { echo "project path not found: $1"; exit 1; }
NAME="${2:-$(basename "$PROJECT")}"
DEST="$VAULT/raw/repos/$NAME"
```

**Pre-flight:** `$PROJECT/graphify-out/graph.json`이 없으면 중단하고 안내:
> graphify가 $PROJECT 에서 아직 실행되지 않았습니다. 프로젝트에서 `/graphify .`를 먼저 돌린 뒤 다시 `/wiki ingest`를 호출하세요.

## 2. graphify 산출물 갱신 (3단계 — community 라벨 보존)

graphify는 community 라벨링을 단일 명령으로 처리하지 않는다 (그쪽 SKILL의 Step 5는 외부 LLM이 채우는 수동 단계). `.graphify_labels.json`이 없거나 community 수와 어긋난 상태에서 `--wiki`를 함께 돌리면 `graphify/wiki.py`가 `Community {cid}` placeholder를 파일명으로 굳히고(`_safe_filename(label)` → `Community_0.md` 등), 매 export마다 기존 `wiki/*.md`를 전부 삭제 후 재생성하므로 이전의 사람-라벨까지 날아간다.

그래서 3단계로 분리한다:

**2a. graph만 갱신 (wiki export 제외, incremental — 소스 변경 없으면 빠름):**
```bash
(cd "$PROJECT" && graphify . --update --no-viz)
```

**2b. community 라벨 검증 및 보강:**
```bash
ANALYSIS="$PROJECT/graphify-out/.graphify_analysis.json"
LABELS="$PROJECT/graphify-out/.graphify_labels.json"
[ -f "$ANALYSIS" ] || { echo "analysis missing — graphify did not produce communities. abort."; exit 1; }
```

- `$ANALYSIS`의 `communities` 키 목록과 `$LABELS`(있다면)의 키 목록을 비교한다.
- `$LABELS`가 없거나, 키 집합이 다르거나, 어떤 라벨이 `^Community \d+$` 패턴이면 → **누락된 cid 각각에 대해** `$ANALYSIS.communities[cid]` 안의 node label들을 읽고 2~5단어의 사람이 읽을 이름을 만들어 라벨 dict에 채운다.
- 채운 결과로 `$LABELS`를 덮어쓴다 (JSON, key는 문자열, `ensure_ascii=False` 상응).
- 라벨이 이미 완전하고 placeholder가 없으면 no-op.

**2c. 검증된 라벨로 wiki export:**
```bash
(cd "$PROJECT" && graphify export wiki)
```

이 시점에 `$PROJECT/graphify-out/wiki/`의 파일명은 모두 사람-라벨 기반이다. `Community_N.md` / `Cluster_N.md`가 하나라도 보이면 2b 실패 → 중단하고 사용자에게 보고한다.

## 3. vault raw 레이어로 스냅샷

```bash
mkdir -p "$DEST"
rsync -a --delete "$PROJECT/graphify-out/wiki/" "$DEST/"
COMMIT=$(cd "$PROJECT" && git rev-parse --short HEAD 2>/dev/null || echo n/a)
FILES=$(find "$DEST" -type f -name '*.md' | wc -l | tr -d ' ')
printf '\n## [%s] sync | raw/repos/%s (%s, %s files)\n' "$TODAY" "$NAME" "$COMMIT" "$FILES" >> "$VAULT/wiki/log.md"
```

## 4. `wiki/sources/summary-<name>.md` 합성

`$DEST/index.md`(graphify가 만든 wiki 인덱스)와 node 수 상위 community 페이지들을 읽고 작성:

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

본문 섹션 (순서대로):
- **TL;DR** — 1~2문장. 이 프로젝트는 무엇인가?
- **주요 모듈** — god node / 큰 community를 한 줄 목적과 함께
- **진입점** — entry-point 파일·API (그래프에서 식별 가능하면)
- **외부 의존성** — 핵심 외부 라이브러리·서비스
- **인용 가능한 발췌** — 핵심 주장을 담은 짧은 스니펫
- **Open questions** — 모호함·갭

## 5. concept / entity 페이지 — 교차참조 우선

vault의 `CLAUDE.md` "교차참조 & 페이지 밀도" 규칙을 따른다:
- 여러 community에 걸쳐 등장하고 *다른 소스와도 재사용될* 개념 → `wiki/concepts/<kebab>.md` 생성/갱신, `sources:`에 이 소스 추가.
- 조직·제품·인물 → `wiki/entities/<kebab>.md`.
- 기존 페이지에 닿는 개념이면 신규 생성보다 **기존 페이지의 `related:`·본문 링크 갱신**을 우선한다.
- 단일 소스에만 등장하는 사소한 god node는 summary 안에 임베드한다 (신규 stub 양산 금지).
- 모순 발견 시 vault CLAUDE.md의 "모순 플래깅" 절차 적용.

## 6. index & log 갱신

- `wiki/index.md`에 신규 페이지를 카테고리별로 `[제목](경로) — 한 줄 요약` 형태로 추가. 기존 항목 보존.
- 로그 append:
```bash
printf '\n## [%s] ingest | %s → wiki/sources/summary-%s.md (+%s concepts, +%s entities)\n' "$TODAY" "$NAME" "$NAME" "$NEW_C" "$NEW_E" >> "$VAULT/wiki/log.md"
```

## 7. 보고

```
Ingested $NAME.
  raw/repos/$NAME/                ($FILES files synced, commit $COMMIT)
  wiki/sources/summary-$NAME.md   (created/updated)
  wiki/concepts/...               ($NEW_C new, $UPD_C updated)
  wiki/entities/...               ($NEW_E new, $UPD_E updated)
  wiki/index.md                   (updated)
```
