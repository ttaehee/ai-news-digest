# STATUS

진행 상황 트래커. 자세한 설계는 [PLAN.md](./PLAN.md), 행동 규칙은 [AGENTS.md](./AGENTS.md).

## 완료
- **0단계** — 프로젝트 뼈대 (`chore: init project skeleton`, `b955f1c`)
- **0.5** — private 원격 저장소 생성 ([ttaehee/ai-news-digest](https://github.com/ttaehee/ai-news-digest))
- **1단계** — 소스 플러그인 + RSS + 피드 헬스체크 하네스 (`feat: add source plugin interface, RSS source, and feed health-check harness`, `30991f8`)
- **2단계** — arXiv 소스 + 카테고리별 top-30 컷 (`feat: add arXiv source with per-category top-30 cap`, `4ec7438`)
- **3단계** — 정규화 + 26h 시간 윈도우 필터 (`feat: add normalization with 26h time-window filter`, `dd26cbd`)
- **4단계** — AI 가공: Claude tool-use 강제 + 재시도/폴백/분할-머지 (`feat: add Claude aggregation via forced tool-use`, `5f0f690`)
- **5단계** — 발송 인터페이스 + 콘솔 렌더러(완전 동작) + Slack/Email 스캐폴드 (`feat: add delivery interface, console renderer, and slack/email stubs`, `5d3d183`)
- **PLAN v3** — LLM 제공자 추상화 계획 반영 (`docs: plan LLM provider abstraction (gemini default, claude alt)`, `ae41e73`)
- **5.5단계** — LLM 제공자 추상화 (gemini 기본 / claude 대안) + Gemini 한국어 키 실호출 검증 통과 (`feat: abstract LLM provider behind LLM_PROVIDER (gemini default, claude alt)`, `c84cd85`)

## 다음
**6단계** — 파이프라인 + dry-run CLI: `pipeline.py`, `__main__.py`, `scripts/run_local.sh`. 실제 `python -m ai_news_digest` 실행해 10개 소스 수집 → 선택 provider 호출 → 콘솔 출력까지 동작 확인(기본 `LLM_PROVIDER=gemini` + `GEMINI_API_KEY`). PLAN §9 row 6 참고.

## 이어가는 법
새 세션에서:

> STATUS.md랑 PLAN.md 보고 다음 단계부터 이어서 하자

## 갱신 규칙
단계 끝낼 때마다 이 파일만 갱신한다:
- **완료**에 한 줄 추가 (`단계 — 설명 (커밋 메시지, 해시)`)
- **다음**을 PLAN.md의 그다음 단계로 교체
