# LLM Wiki Schema (Karpathy Pattern)

이 vault는 Andrej Karpathy의 LLM Wiki 패턴을 따른다.
참조: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

## 3-Layer 아키텍처

1. **Raw Sources (`raw/`)** — immutable. 외부에서 가져온 원본 자료. 절대 수정하지 말 것
2. **Wiki (`wiki/`)** — LLM이 소유. raw/를 컴파일한 결과물
3. **Schema (`CLAUDE.md`)** — 이 파일. 에이전트를 wiki maintainer로 변환하는 규칙

## 디렉토리 레이아웃

- `raw/articles/` — 블로그·뉴스·클리핑 (`YYYY-MM-DD-slug.md`)
- `raw/papers/` — 논문 PDF
- `raw/repos/` — 외부 레포 README, graphify export 산출물
- `raw/data/` — 벤치마크, CSV, JSON
- `raw/images/` — 다이어그램, 스크린샷
- `raw/assets/` — Obsidian 첨부파일 기본 경로
- `wiki/index.md` — 전체 카탈로그 (카테고리별)
- `wiki/log.md` — append-only 활동 로그
- `wiki/overview.md` — 지식 베이스 전체 합성 요약
- `wiki/concepts/` — 개념·이론·패턴
- `wiki/entities/` — 인물·조직·제품
- `wiki/sources/` — raw/ 항목별 요약 (1:1 매핑)
- `wiki/comparisons/` — 비교·대조 페이지

## 페이지 프론트매터

모든 wiki 페이지는 YAML frontmatter 필수:

- `title` — Human-readable 제목
- `type` — `concept | entity | source-summary | comparison`
- `sources` — 참조한 raw/ 파일 경로 배열
- `related` — 링크된 다른 wiki 페이지
- `created` — `YYYY-MM-DD`
- `updated` — `YYYY-MM-DD`
- `confidence` — `high | medium | low`

## 페이지 유형별 규칙

- **concept (`wiki/concepts/`)** — 개념·알고리즘·패턴. "무엇이고 왜 중요한가" 중심
- **entity (`wiki/entities/`)** — 인물·조직·제품·모델. 핵심 사실 + 관련 작업 + 관계
- **source-summary (`wiki/sources/`)** — raw/ 단일 항목의 압축 요약 (1:1 매핑)
- **comparison (`wiki/comparisons/`)** — N개 항목을 같은 축에서 비교. 표 권장

## 특수 파일

- `wiki/index.md` — 카테고리별 카탈로그. 신규·삭제 시 반드시 갱신
- `wiki/log.md` — append-only. 절대 과거 항목 수정 금지. 포맷: `## [YYYY-MM-DD] <operation> | <description>` (operation: `init | sync | ingest | query | lint | synthesis`)
- `wiki/overview.md` — 전체 high-level 합성. 주기적으로 다시 쓰기

## 워크플로

주요 워크플로는 `/wiki` skill을 통해 실행:

- `/wiki ingest-project <path>` — graphify 산출물을 raw/repos/ 로 가져와 wiki/sources/ 로 요약
- `/wiki ingest-url <url>` — URL을 raw/articles/ 로 저장하고 요약
- `/wiki ingest-file <path>` — 로컬 파일을 raw/ 적절한 위치에 저장하고 요약
- `/wiki query "<question>"` — wiki를 통해 답변. 새 합성은 페이지로 저장
- `/wiki lint` — 고아·frontmatter·sources 경로·stale 점검
- `/wiki overview` — overview.md 재합성

## graphify 연동

이 vault는 **consumer-only**. graphify는 vault 안에서 절대 실행하지 않는다 (운영 안정성: ingest 중 graph가 바뀌면 라벨 매핑이 깨진다).

`/wiki ingest-project <project-path>` 흐름:

1. `graphify update <project>` (no LLM) — graph만 갱신
2. `graph.json`의 `node.community` 필드로 communities dict 빌드
3. Claude가 graphify의 LLM 자리를 대체해서 라벨 100% coverage 부여
4. `graphify.wiki.to_wiki()` Python API 직접 호출로 wiki 재생성 (LLM 키 불필요)
5. `graphify-out/wiki/` → `raw/repos/<name>/` 로 rsync --delete
6. Claude가 `wiki/sources/summary-<name>.md` 작성
7. 새 개념·인물은 wiki/concepts/, wiki/entities/에 페이지 생성
8. wiki/index.md, wiki/log.md 갱신

### 라벨 커버리지 규칙

ingest 완료 후 `raw/repos/<name>/`에 `Community_NN.md` / `Cluster_NN.md` placeholder가 하나도 남으면 안 된다 (100% coverage). 이유: placeholder는 retrieval 가치가 없고, 사용자가 vault를 탐색할 때 의미없는 파일명이 신호 대 잡음비를 떨어뜨린다.

라벨 정책:
- **size ≥ 3 community** → Claude가 top nodes 보고 **영어 큐레이션**. 영어 기본 이유: (a) graphify의 노드 라벨이 코드 식별자라 영어 위주, (b) 한국어 토큰 소모가 큼, (c) 검색 용어 일관성. 도메인 고유명사가 한국어로 굳어진 경우(예: `테토디`, `행정구역`, `Coway Dept API`)에만 예외적 한국어 혼용.
- **size 1-2 community** → top node의 `label` 그대로 사용 (deterministic, 토큰 소모 없음).

### 외부 graphify 끼어듦 회복

누군가 `graphify .` 풀 파이프라인을 돌려 `labels.json`이 LLM 영어 라벨로 덮어쓰여진 경우, `raw/repos/<name>/`의 기존 큐레이션 파일에서 "Key Concepts" top-node를 추출해 새 graph의 community id로 voting → greedy하게 라벨 복구한다 (skill의 `scripts/recover_labels.py`).

## Obsidian 설정

- Attachment folder path → `raw/assets/`
- Default view mode: preview
- `alwaysUpdateLinks: true`

## 절대 규칙

이 규칙들은 wiki의 신뢰성을 유지하는 invariant다. 위반하면 retrieval이 깨지거나 데이터 손실이 발생한다.

- `raw/` 파일은 절대 수정하지 말 것 — immutable 원본 보장이 깨지면 wiki의 출처 추적이 무의미해진다
- `wiki/log.md` 는 append-only — 과거 활동 기록은 audit trail
- frontmatter 없는 wiki 페이지 생성 금지 — lint와 retrieval이 frontmatter를 전제로 동작
- `wiki/index.md` 갱신 없이 새 wiki 페이지 생성 금지 — 카탈로그에 없는 페이지는 발견 불가능
- vault 안에서 graphify 직접 실행 금지 — consumer-only 원칙
- `/wiki ingest-project` 후 placeholder 라벨(`Community_NN.md`, `Cluster_NN.md`) 잔존 금지 — 100% coverage 보장
