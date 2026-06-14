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
- **6단계 fix** — 분할 호출에서 한쪽만 폴백일 때 진짜 요약이 살아남으면 폴백 배너 안 띄우게 머지 로직 정정 (`fix: clear merge fallback flag when fallback items don't survive top-5`, `8d2d40d`)
- **6단계** — 파이프라인 + dry-run CLI: `pipeline.py`/`__main__.py`/`config.py`/`scripts/run_local.sh` + 실호출 E2E 검증 통과 (`feat: wire end-to-end pipeline with dry-run CLI`, `859a829`)
- **8단계** — GitHub Actions: `digest.yml`(매일 UTC 00시 cron + `workflow_dispatch`, 기본 `DRY_RUN=true`), `ci.yml`(pytest + gitleaks). workflow_dispatch 실행 1회 통과: 12 소스 / 2167 raw / 26h 윈도우 99 / 49+50 분할 / 양쪽 Gemini 성공 / 12개 항목 진짜 요약 / fallback=False / 총 205s (`ci: add daily digest workflow and CI`, `d84af9c`). (7단계는 PLAN §9에서 DRY_RUN으로 갈음하기로 정해 스킵.)
- **9단계** — README: 동작 방식·로컬 실행·GHA secrets·cron 변경법(UTC + 지터 안내)·환경변수·현재 한계 (`docs: add README with setup and ops guide`, `e4c8ff2`)
- **개선#1 (AI 재시도 backoff)** — `_attempt_with_retry`에 10초 sleep 삽입. 테스트는 autouse fixture로 `time.sleep` 모킹 (`feat: back off 10s between AI retry attempts`, `af0eaa8`)
- **개선#2 (GHA Node 24)** — `actions/checkout@v4`→@v6, `actions/setup-python@v5`→@v6로 두 워크플로 모두 업데이트. 2026-06-16 강제 전환 전 마이그레이션 완료 (`ci: bump actions/checkout to v6 and actions/setup-python to v6`, `266177e`)
- **fix (digest.yml DRY_RUN)** — schedule 트리거가 `null == false` loose equality 때문에 `DRY_RUN=False`로 떨어지던 expression을 `github.event_name == 'workflow_dispatch'` 가드로 수정. workflow_dispatch 1회 통과: DRY_RUN=True, 양쪽 Gemini 성공, fallback=False, 6개 항목 진짜 한국어 요약, 173s (`fix: gate digest DRY_RUN expression on workflow_dispatch event`, `8b4240f`)
- **개선#3 (SlackSender 활성화)** — 스텁 제거하고 `httpx.post(webhook, json={"text": render_text(...)})` + `raise_for_status` 실제 구현. `render.py` 공용 포맷터 재사용 → 콘솔과 동일 본문. respx 모킹 테스트 10개(생성자 2 + send 8: 본문/헤더/failed_sources/단일호출/4xx/5xx/네트워크 에러) (`feat: implement SlackSender via httpx POST to incoming webhook`, `0ae4537`)
- **개선#4 (workflow Slack 전환 + window_hours 입력)** — schedule 트리거 매일 자동 Slack 발송, workflow_dispatch에 `window_hours` 입력 추가(주말 catch-up 용) (`ci: ship digest to Slack on schedule + add window_hours dispatch input`, `61b53df`)
- **개선#5 (디지스트 사이즈 축소)** — TOP_PER_CATEGORY 5→3. 출력 최대 20→12 항목 (`feat: cap each category at 3 items (was 5)`, `ef5dd96`)
- **개선#6 (요약 1줄 압축)** — `DigestItem.summary_kr` `tuple[str,str,str]`→`str`, 시스템 프롬프트/스키마/렌더러 일괄. 부수효과로 Gemini 호출 시간 ~170s→30~60s로 축소 (`feat: condense item summary to a single inline line`, `f8e01b1`)
- **개선#7 (Slack mrkdwn 렌더러 분리)** — `delivery/slack.py`에 `_render_slack` 신설: `*bold*` 카테고리, `<url|title>` 클릭 가능 링크, 카테고리 사이 빈 줄. 콘솔 `render.py`는 그대로 (`feat: render Slack output with mrkdwn bold + link-wrapped titles`, `5302ff1`)
- **fix (스키마 notes 제거)** — 모델이 매번 "AI 뉴스 다이제스트입니다" 같은 군더더기로 채우던 `notes` 필드를 두 provider 스키마에서 제거. 폴백 경로는 그대로 (`fix: stop emitting boilerplate "메모: ..." footer`, `79073e6`)
- **개선#8 (Slack 리스트 시각)** — `-`→`•` 불릿 + 🌵/📖/🍄‍🟫/🌿 이모지 카테고리 헤더. `_render_slack`만 변경 (`feat: render Slack list with bullets and emoji category headers`, `38b82a8`)

## 다음
**본 라인업 완료 + 슬랙 프로덕션 안착.** 매일 KST 09시(UTC 00시)에 자동 Slack 발송. 다음 작업은 아래 "다음에 개선" 항목들에서 선택.

## 다음에 개선 (작은 후속 작업, 본 라인업과 별개)
- **Hacker News 소스 추가** — 1차 소스 원칙으로 PLAN §4에서 제외했지만, 사람들 반응·화제성 신호를 잡으려고 재검토. Algolia API(`https://hn.algolia.com/api/v1/search_by_date?tags=story&query=AI`) 등으로 RSS-like fetch 가능.
- **Anthropic 소스 검토** — 공식 RSS 미제공으로 PLAN §4에서 드롭했지만, 그 후 추가됐는지 다시 확인. 여전히 없으면 sitemap 폴링이나 다른 우회 검토.
- **EmailSender 활성화** — SMTPConfig 검증까지 작성된 스캐폴드. SMTP 자격증명 채우고 `smtplib`로 실 발송 구현하면 끝. Slack과 같은 패턴.

## 이어가는 법
새 세션에서:

> STATUS.md랑 PLAN.md 보고 다음 단계부터 이어서 하자

## 갱신 규칙
단계 끝낼 때마다 이 파일만 갱신한다:
- **완료**에 한 줄 추가 (`단계 — 설명 (커밋 메시지, 해시)`)
- **다음**을 PLAN.md의 그다음 단계로 교체
