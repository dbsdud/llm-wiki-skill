# Lint — wiki health-check

`/wiki lint`의 상세 체크리스트. Karpathy 원문의 lint 정의를 충실히 구현한다:

> "주기적으로 LLM에게 위키를 health-check 시킨다. 페이지 간 모순, 새 소스가 뒤집은 낡은 주장,
> inbound 링크 없는 orphan, 언급되지만 자기 페이지가 없는 중요 개념, 누락된 교차참조, 데이터 갭을 찾는다."

대상: `$VAULT/wiki/**/*.md` (단 `index.md`, `log.md`, `overview.md`는 frontmatter/orphan 검사 제외).

## 두 종류의 검사

**기계적 검사** (스크립트로 결정 가능 — 빠르고 신뢰성 높음):
가능하면 grep/스크립트로 처리한다. 눈으로 훑지 않는다.

**의미적 검사** (LLM 판단 필요):
페이지 내용을 읽고 판단한다. 가장 비싸지만 위키의 진짜 가치.

---

## 기계적 검사

### M1. Frontmatter 완전성
각 페이지에 필수 필드 존재 확인: `title`, `type`, `sources`, `related`, `created`, `updated`, `confidence`.
타입별 추가 필드 (`decision` → `status`).

### M2. Broken sources
각 페이지 `sources:` 배열의 경로가 `$VAULT` 기준으로 실재하는지 확인.

### M3. Orphan (inbound 링크 0)
다른 wiki 페이지에서 `[..](path)` 또는 `[[wikilink]]`로 참조되지 않는 페이지.
grep으로 각 페이지 파일명/경로의 피참조 횟수를 센다.

### M4. Stale (날짜)
`updated:`가 `$TODAY` 기준 90일 이상 지난 페이지. 후속 의미 검사(S2) 후보.

---

## 의미적 검사

### S1. 페이지 간 모순
서로 관련된 페이지들(같은 개념/인물을 다루거나 `related:`로 엮인)을 비교해 사실 충돌을 찾는다.
발견 시: 어느 쪽이 더 최신/신뢰도 높은지 판단, vault CLAUDE.md "모순 플래깅" 절차로 표시·갱신 제안.

### S2. Superseded (낡은 주장)
M4의 stale 후보 + 더 최신 소스가 들어온 주제에 대해, 옛 주장이 새 소스에 의해 뒤집혔는지 확인.
뒤집혔으면 본문 갱신 + `superseded`/`confidence: low` 표시 제안.

### S3. 페이지 없는 중요 개념
source-summary·concept 본문에서 **반복적으로 언급되지만** 자기 페이지가 없는 개념/인물을 찾는다.
여러 소스에 걸쳐 재사용된다면 신규 페이지 생성 제안 (단일 소스 한정이면 임베드 유지).

### S4. 누락 교차참조
A가 B의 주제를 다루는데 A의 `related:`/본문에 B 링크가 없는 경우. 링크 추가 제안.
이것이 위키 밀도의 핵심 — 인색하게 굴지 않는다.

### S5. 데이터 갭
overview의 "미해결 질문", source-summary의 "Open questions"에서 반복되는데
아직 어떤 소스도 답하지 않은 주제. 다음 소싱 방향으로 사용자에게 제시.

---

## 보고 & 자동수정

결과를 체크리스트로 보고한다. **안전한 항목만 자동수정**:
- 누락 `updated:` → 현재 날짜 추가
- 비-index 페이지의 누락 `confidence:` → `medium` 추가

나머지(모순 해소, 페이지 생성/삭제, 교차참조 추가, superseded 판정)는 **사용자에게 제안하고 승인받는다** — 위키 내용을 임의로 재작성하지 않는다.

로그 append:
```bash
printf '\n## [%s] lint | %s orphan / %s frontmatter / %s broken-src / %s contradiction / %s missing-page / %s missing-xref\n' \
  "$TODAY" "$ORPHANS" "$FM" "$SRC" "$CONTRA" "$MISSP" "$MISSX" >> "$VAULT/wiki/log.md"
```
