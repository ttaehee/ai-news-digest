# STATUS

진행 상황 트래커. 자세한 설계는 [PLAN.md](./PLAN.md), 행동 규칙은 [AGENTS.md](./AGENTS.md).

## 완료
- **0단계** — 프로젝트 뼈대 (`chore: init project skeleton`, `b955f1c`)
- **0.5** — private 원격 저장소 생성 ([ttaehee/ai-news-digest](https://github.com/ttaehee/ai-news-digest))
- **1단계** — 소스 플러그인 + RSS + 피드 헬스체크 하네스 (`feat: add source plugin interface, RSS source, and feed health-check harness`, `30991f8`)
- **2단계** — arXiv 소스 + 카테고리별 top-30 컷 (`feat: add arXiv source with per-category top-30 cap`, `4ec7438`)
- **3단계** — 정규화 + 26h 시간 윈도우 필터 (`feat: add normalization with 26h time-window filter`, `dd26cbd`)

## 다음
**4단계** — AI 가공 (Claude API, tool-use 강제, 모킹 테스트). PLAN §9·§5 참고.

## 이어가는 법
새 세션에서:

> STATUS.md랑 PLAN.md 보고 다음 단계부터 이어서 하자

## 갱신 규칙
단계 끝낼 때마다 이 파일만 갱신한다:
- **완료**에 한 줄 추가 (`단계 — 설명 (커밋 메시지, 해시)`)
- **다음**을 PLAN.md의 그다음 단계로 교체
