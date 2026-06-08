# AI 뉴스 다이제스트 봇 — 구현 계획

> 이 문서는 사용자 확인을 받기 위한 **계획서**다. 본 계획에 대한 OK를 받은 뒤에만
> 단계별로 구현 → 검증 → 커밋 순으로 진행한다.

---

## 1. 결론 요약 (TL;DR) — 사용자 OK 반영 v2

- **언어/스택**: Python 3.11+. 표준 라이브러리 + 최소한의 외부 의존성.
- **수집**: 1차 소스 9곳 + arXiv(cs.AI/CL/LG) = 총 10개. 모두 무료/공개·실제 200·파싱 확인 완료.
  공식 RSS가 없는 Anthropic/Meta AI/Mistral은 **드롭**(2차 매체로 메우지 않음).
  중복 방지는 시간 윈도우(`WINDOW_HOURS=26`)로 처리 — 26시간으로 잡아 cron 지터 ~2h 흡수.
- **AI**: Anthropic Claude Haiku 4.5 기본. 구조화 출력은 **tool-use 강제** 방식(Anthropic API엔 `response_format` 없음).
  필요 시 분할 호출, 비용 최소화. 품질 부족하면 추후 Sonnet 4.6 승격 검토.
- **arXiv 입력 제어**: 카테고리당 최신 30건만 수집(피드 단계에서 컷). 토큰 폭주 방지.
- **발송**: 끝까지 **DRY_RUN(콘솔)으로만 구현·검증**. 슬랙/메일은 Sender 인터페이스 + 모듈 골격만 만들어 두고
  실 발송은 사용자가 추후 시크릿 채워서 직접 켠다. (코드만 준비, 우선순위: 메일 → 슬랙)
- **실행**: GitHub Actions cron, 매일 KST 09시(=UTC 00시) 트리거.
- **보안**: 시크릿은 환경변수+GitHub Secrets, pre-commit + CI에서 gitleaks로 차단.
- **저장소**: 로컬 git init. 0단계 검증·커밋 후 `gh repo create ai-news-digest --private`로 원격 생성·푸시.
  푸시 직전 `.env`가 `.gitignore`에 있고 커밋된 파일에 시크릿이 없는지 재검사.
- **품질**: 단위테스트는 모킹, 실제 외부 호출은 통합 단계에서 검증.

---

## 2. 기술 스택 결정

### 언어: Python 3.11+

**선택 이유**
- RSS 파싱(`feedparser`), HTTP(`httpx`), Anthropic SDK 모두 가장 성숙.
- GitHub Actions의 `setup-python` 으로 캐시 포함 1줄 셋업.
- 표준 라이브러리만으로도 JSON/시간/로깅 처리가 깔끔.
- 단일 파일로도 굴릴 수 있을 만큼 가볍고, 의존성 잠금(`requirements.txt`)이 단순.

**비교 후 탈락**
- **Node/TS**: 가능하지만 RSS/arXiv 처리는 Python 대비 잡일이 늘고 의존성 트리가 깊어진다.
- **Go/Rust**: 컴파일 단계가 GHA 캐시·디버깅 비용을 증가시킨다. 이 규모엔 과잉.

### 의존성 (최소)
- `feedparser` — RSS/Atom 파싱
- `httpx` — HTTP 호출(타임아웃·재시도 깔끔). `requests`도 후보지만 비동기까지 고려해 `httpx`.
- `anthropic` — Claude API SDK
- `python-dateutil` — 날짜 파싱(피드별 포맷 편차 흡수)
- 개발 의존성: `pytest`, `pytest-mock`, `respx`(httpx 모킹), `pre-commit`, `gitleaks`(바이너리는 pre-commit 훅이 가져옴)

> 모든 외부 호출은 인터페이스로 추상화해 테스트에서는 모킹한다.

---

## 3. 아키텍처 / 디렉터리

```
ai-news-digest/
├── AGENTS.md                        # 단일 규칙 소스 (이 프로젝트의 진짜 룰북)
├── CLAUDE.md                        # 한 줄짜리 포인터: @AGENTS.md
├── README.md                        # 로컬 실행/Secrets/cron 변경 안내
├── PLAN.md                          # (본 문서)
├── .env.example                     # 시크릿 키 이름만, 값은 비움
├── .gitignore
├── .pre-commit-config.yaml          # gitleaks + 기본 훅(end-of-file 등)
├── pyproject.toml                   # 또는 requirements.txt + requirements-dev.txt
├── .github/
│   └── workflows/
│       ├── digest.yml               # 매일 다이제스트 실행
│       └── ci.yml                   # PR/Push: 테스트 + 시크릿 스캔
├── src/
│   └── ai_news_digest/
│       ├── __init__.py
│       ├── __main__.py              # `python -m ai_news_digest` 진입점
│       ├── config.py                # 환경변수/기본값 로드
│       ├── logging_setup.py
│       ├── pipeline.py              # 4단계 오케스트레이션
│       ├── sources/
│       │   ├── __init__.py
│       │   ├── base.py              # Source 추상 클래스(플러그인 인터페이스)
│       │   ├── rss.py               # 일반 RSS 소스
│       │   ├── arxiv.py             # arXiv API 소스
│       │   └── registry.py          # 활성 소스 목록 (여기만 고치면 추가/교체)
│       ├── normalize.py             # {title, url, source, published_at, raw_text}
│       ├── ai_processor.py          # Claude 호출 + JSON 검증/재시도/분할
│       ├── delivery/
│       │   ├── __init__.py
│       │   ├── base.py              # Sender 인터페이스
│       │   ├── slack.py
│       │   └── email_smtp.py        # 옵션
│       └── render.py                # Slack 블록/메일 본문 포맷터
├── tests/
│   ├── fixtures/
│   │   ├── openai_rss.xml
│   │   ├── arxiv_response.xml
│   │   └── claude_response.json
│   ├── test_sources_rss.py
│   ├── test_sources_arxiv.py
│   ├── test_normalize.py
│   ├── test_ai_processor.py
│   ├── test_delivery_slack.py
│   └── test_pipeline.py
└── scripts/
    └── run_local.sh                 # `.env` 로드 + dry-run 한 줄 실행
```

### 플러그인 구조 (소스 추가/교체)
- `sources/base.py`에 `class Source(Protocol)` 정의:
  - `name: str`, `kind: Literal["rss","api"]`, `fetch(window_hours: int) -> list[RawItem]`
- 새 소스는 `Source`만 구현해서 `registry.py`의 리스트에 추가하면 끝.
- 한 소스 실패가 전체를 막지 않도록 `pipeline`에서 소스별 try/except + 로그.

### 파이프라인 단계 (4단계, AI는 3번에만)
1. **수집** `collect()` — registry 순회, 각 source.fetch() 병렬(스레드풀, 타임아웃 10s). 실패 격리.
2. **정규화** `normalize()` — 통일 스키마 + 시간 윈도우 필터(`WINDOW_HOURS`, 기본 24).
3. **가공(AI)** `process_with_claude()` — 1회 호출로 끝내되, 토큰 한도 초과 시 입력을 분할 호출 후 결과 머지.
4. **발송** `deliver()` — 자가점검 통과 시 Slack로. `DRY_RUN=1`이면 stdout으로만.

### 자가점검(검증 루프)
- 수집 결과 0개 → 발송 중단(로그만 남김, exit code 0으로 정상 종료).
- Claude JSON 파싱 실패 → 1회 재시도(`"JSON만 반환하라"` 프롬프트 강화), 그래도 실패면 원본 링크 덤프 폴백 메시지로 발송.
- 요약 비어있음 → 해당 카테고리에 한해 1회 재시도.

### 관찰성
- `logging` 표준 모듈, 단계 진입/종료에 (수집 개수 / 소요 ms / 실패 소스 목록) 한 줄 로그.
- 실패한 소스 이름은 최종 Slack 메시지 푸터에 "(일부 소스 실패: …)" 형태로 표시.

---

## 4. 수집 소스 (실측 검증 완료 — 최종)

> 사용자 지시 반영: 2차 매체(VentureBeat/MarkTechPost 등)와 개별 연구자 블로그는 제외.
> 공식 RSS가 없는 소스는 2차로 메우지 않고 **드롭**.

### 채택 (10개) — 모두 실측 200 + 파싱 확인

| # | 소스 | 종류 | URL | 영역 / 채택 이유 |
|---|------|------|-----|-------------------|
| 1 | OpenAI Blog | RSS | `https://openai.com/blog/rss.xml` | 모델/제품 1차 |
| 2 | Google DeepMind Blog | RSS | `https://deepmind.google/blog/rss.xml` | 연구/모델 1차 |
| 3 | Google Research Blog | RSS | `https://research.google/blog/rss/` | 연구 1차 |
| 4 | Google Blog — AI 카테고리 | RSS | `https://blog.google/technology/ai/rss/` | 회사 공식 AI 제품 뉴스(Gemini/Workspace) — DeepMind/Research와 보완 |
| 5 | Microsoft Research | RSS | `https://www.microsoft.com/en-us/research/feed/` | 연구 1차(Phi 등) |
| 6 | Hugging Face Blog | RSS | `https://huggingface.co/blog/feed.xml` | 툴/오픈모델 허브 |
| 7 | Stability AI News | RSS | `https://stability.ai/news-updates?format=rss` | 생성모델 1차 |
| 8 | NVIDIA Blogs | RSS | `https://blogs.nvidia.com/feed/` | 인프라/플랫폼 1차 |
| 9 | BAIR (Berkeley AI Research) | RSS | `https://bair.berkeley.edu/blog/feed.xml` | 학계 1차(빈도 낮음 — 빈 결과 허용) |
| 10 | arXiv `cs.AI` / `cs.CL` / `cs.LG` | RSS | `http://export.arxiv.org/rss/{cat}` | 논문 1차 공식 무료 피드 |

### 드롭 (공식 RSS 미제공 — 2차 매체로 메우지 않음)

| 소스 | 결과 |
|------|------|
| Anthropic News | `news/rss.xml`·`feed.xml`·기타 후보 전부 404. sitemap만 존재. 드롭. |
| Meta AI Blog (ai.meta.com) | `blog/rss/`·`feed/`·sitemap 전부 404. 드롭. |
| Mistral AI | `news/rss`·`rss.xml`·`?format=rss` 전부 HTML. 드롭. |

> 채택한 RSS URL은 그대로 `registry.py`에 박는다. arXiv는 카테고리별 최신 30건만 컷(토큰 보호, §5 참조).

### 제외 (이유 명시)

| 소스 | 제외 이유 |
|------|-----------|
| Twitter/X | 무료 API 폐쇄·종량제. |
| Reddit (r/MachineLearning 등) | 노이즈 큼·OAuth 필요·rate limit. 1차 우선 원칙. |
| Hacker News | 2차 큐레이션. 1차 우선 원칙. |
| VentureBeat / MarkTechPost / TechCrunch | 2차 매체·광고·노이즈. 사용자 명시 제외. |
| Stratechery 등 유료 뉴스레터 | 유료 제외 규칙. |
| 개별 연구자 블로그(lilianweng, raschka, alignmentforum 등) | 사용자 명시 제외(기본 목록에 안 넣음). 필요 시 추후. |

### 중복 발송 방지 (서버/DB 없이)
- **시간 윈도우 필터만 사용.** `WINDOW_HOURS=26` (기본).
- 각 항목 `published_at`이 `now - WINDOW_HOURS` 이후인 것만 통과.
- arXiv는 `pubDate` 필드 사용.
- `published_at`을 못 구하는 항목은 보수적으로 제외(개인정보·노이즈 유입 방지).
- 26h를 택한 이유: 24h 기본 주기 + GHA cron 지터(수 분~수십 분) 흡수용 ~2h 오버랩.

---

## 5. AI 처리 (Claude API)

### 호출 정책
- 모델: `claude-haiku-4-5-20251001` (요약 작업엔 충분, 비용 ↓). 품질 부족 시 `claude-sonnet-4-6`으로 1단계 승격.
- 입력은 정규화된 항목 리스트(`title`, `url`, `source`, `published_at`, `raw_text` 요약 1000자 컷).
- **arXiv는 수집 단계에서 카테고리별 최신 30건 컷.** 다른 소스는 그대로 흘려보내되, 전체 항목 수가
  많아 토큰 한도가 위험하면 분할 호출.
- **구조화 출력 강제 방식**: Anthropic API엔 `response_format`이 없으므로 두 가지 중 선택해 구현:
  1. **tool-use 강제**(권장): 단일 도구 `emit_digest`를 정의하고 `tool_choice={"type":"tool","name":"emit_digest"}`로
     강제 호출 → 응답이 항상 JSON 인자로 들어옴. 파싱·검증 단순.
  2. assistant prefill: 응답을 `{`로 강제 시작하게 prefill. tool-use가 막힐 때만 폴백.
  → 1번 채택. `response_format` 탐색에 시간 쓰지 않음.
- 입력 토큰 한도 초과 시: 항목을 절반으로 나눠 2회 호출 → 결과 머지 후 카테고리별 상위 5 재정렬.
- 프롬프트 캐싱 사용(시스템 프롬프트 + 카테고리/스코어링 규칙은 캐시 블록).

### 기대 출력 스키마
```json
{
  "categories": {
    "모델출시": [
      {
        "title": "...",
        "url": "...",
        "source": "...",
        "importance": 9,
        "summary_kr": ["...", "...", "..."]
      }
    ],
    "논문": [],
    "툴": [],
    "기타": []
  },
  "notes": "선택적 메모(스킵 가능)"
}
```

### 중요도 가이드 (프롬프트에 명시)
- 종합 판단. 단순 합산이 아니라 우선순위:
  ① 업계 파급력(새 모델/주요 API 변경) > ② 출처 신뢰도(1차 소스 우선) > ③ AI 전반 관련성.
  화제성/신규성은 동점 시 보조 지표.
- 각 카테고리에서 importance 내림차순 상위 **최대 5개**만 남김.

### 개인정보 보호
- 시스템 프롬프트에 "개인 이메일/연락처/주소가 본문에 보이면 요약에 절대 포함하지 말 것" 명시.
- 추가로 발송 직전 정규식으로 이메일/전화번호 패턴 1차 차단(이중 안전망).

---

## 6. 발송

> 사용자 결정: **이번 라운드는 DRY_RUN(콘솔 출력)으로만 끝까지 구현·검증한다.**
> Sender 인터페이스 + Slack/Email 모듈 골격은 미리 둔다. 실 발송 검증은 사용자가 시크릿 채워서
> 직접 켤 때까지 보류. 7단계의 실제 발송 검증은 DRY_RUN 출력 확인으로 대체.

### 기본 동작
- `DRY_RUN=1`(기본값으로 둠) → 렌더링된 메시지를 stdout으로만 출력.
- `DRY_RUN=0` + `DELIVERY=slack|email` → 실제 발송.
- `DELIVERY` 미지정 시 안전한 dry-run으로 폴백.

### 추후 켤 때(코드만 준비)
- `delivery/slack.py` — `SLACK_WEBHOOK_URL`로 POST. Block Kit. (스텁: 호출 시 NotImplementedError 대신
  골격만, 실제 HTTP 호출은 추후 단계에서 활성화)
- `delivery/email_smtp.py` — SMTP 환경변수(`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_TO`).
- 두 sender 모두 `Sender` 인터페이스 구현.

### 렌더링(공통, 지금 구현)
- 헤더: `AI 뉴스 다이제스트 — YYYY-MM-DD (KST)`
- 본문: 카테고리별 섹션, 각 항목 `제목 (출처) · 링크` + 3줄 한국어 요약.
- 푸터: 실패 소스 목록(있을 때).
- 콘솔 모드는 동일 본문을 텍스트로 출력(슬랙/메일 포맷터는 같은 데이터 구조 공유).

---

## 7. 보안 / 시크릿

- 코드/README/.env.example 어디에도 실제 키 금지. `.env.example`엔 키 **이름만**.
- `.gitignore`에 `.env`, `.venv/`, 캐시류 포함.
- pre-commit: `gitleaks` + 기본 훅(trailing-whitespace, end-of-file-fixer, check-yaml).
- CI: 동일 gitleaks 잡을 워크플로에 추가해 PR/Push 단계에서도 차단.
- GitHub Secrets에 등록할 키:
  - `ANTHROPIC_API_KEY`
  - `SLACK_WEBHOOK_URL`
  - (옵션) `SMTP_*`, `MAIL_TO`

---

## 8. GitHub Actions

### `digest.yml`
- 트리거: `schedule: - cron: "0 0 * * *"` (UTC 00시 = KST 09시) + `workflow_dispatch`.
- 잡: ubuntu-latest, Python setup + 캐시, 의존성 설치, `python -m ai_news_digest`.
- 환경변수는 Secrets 주입. `DRY_RUN`은 수동 실행 시 input으로 전환 가능.
- README에 명시: **GHA cron은 정시 실행이 보장되지 않으며 수 분~수십 분 지연 가능**.

### `ci.yml`
- 트리거: push/pull_request.
- 잡: pytest + gitleaks. 외부 API 호출은 없음(모킹).

---

## 9. 단계별 진행 계획 (검증 후 커밋, Conventional Commits)

> 각 단계 끝에서 "동작 확인" 항목을 실제로 돌려본 뒤 OK를 받고 커밋한다.

| # | 단계 | 핵심 산출물 | 동작 확인 | 커밋 메시지 |
|---|------|-------------|-----------|-------------|
| 0 | 뼈대 init | `git init` + `.gitignore`(.env 포함) + `pyproject.toml` + `AGENTS.md` + `CLAUDE.md`(@AGENTS.md 포인터) + `.env.example` + `.pre-commit-config.yaml` | `pre-commit run --all-files` 통과, `pytest -q` (0 tests OK) 통과 | `chore: init project skeleton` |
| 0.5 | 원격 저장소 | `gh repo create ai-news-digest --private` + `git push -u origin main` | 푸시 직전 `.gitignore`에 `.env`·`__pycache__` 포함 / `git grep` 시크릿 없음 재확인 | (커밋 없음) |
| 1 | 소스 플러그인 + RSS + 피드 생존 하네스 | `sources/base.py`, `sources/rss.py`, `sources/registry.py`(현 단계엔 RSS 9개 등록; arXiv는 2단계), `scripts/check_feeds.py`(레지스트리 순회해 HTTP/타입/항목 수/최근 날짜/OK·FAIL 표 출력, 하나라도 FAIL이면 exit 1), `tests/test_sources_rss.py`(픽스처·모킹), `tests/test_feeds_live.py`(`@pytest.mark.network` — 기본 CI에선 제외), `tests/conftest.py` + pytest 마커 등록 | `pytest -q`(기본, network 제외) 통과 + `python scripts/check_feeds.py`로 9개 모두 OK | `feat: add source plugin interface, RSS source, and feed health-check harness` |
| 2 | arXiv 소스 (30건 컷) | `sources/arxiv.py` + 카테고리별 상위 30건 컷 + 테스트 | `pytest tests/test_sources_arxiv.py` 통과 | `feat: add arXiv source with per-category top-30 cap` |
| 3 | 정규화 + 시간 윈도우(26h) | `normalize.py` + 테스트 | 단위테스트 통과 | `feat: add normalization with 26h time-window filter` |
| 4 | AI 가공 (tool-use 강제, 모킹) | `ai_processor.py` + `emit_digest` 툴 정의 + 프롬프트 + Claude 응답 모킹 테스트 (분할/재시도/폴백) | 단위테스트 통과 | `feat: add Claude aggregation via forced tool-use` |
| 5 | 발송 골격 + 콘솔 렌더러 | `delivery/base.py` (Sender 인터페이스), `delivery/console.py`(완전 동작), `delivery/slack.py`·`delivery/email_smtp.py`(골격 stub), `render.py`(공통 포맷터) + 콘솔/모킹 테스트 | `pytest tests/test_delivery_console.py` 통과 | `feat: add delivery interface, console renderer, and slack/email stubs` |
| 6 | 파이프라인 + dry-run CLI | `pipeline.py`, `__main__.py`, `scripts/run_local.sh` | **실제로** `python -m ai_news_digest` 실행 → 10개 소스 수집·Claude 호출·콘솔 출력까지 동작 확인 (사용자 ANTHROPIC_API_KEY 필요) | `feat: wire end-to-end pipeline with dry-run CLI` |
| 7 | (생략) 실 발송 검증 | — | DRY_RUN 콘솔 출력으로 갈음. 슬랙/메일 실호출은 사용자가 직접 켤 때 진행. | (없음) |
| 8 | GitHub Actions | `.github/workflows/digest.yml`(매일 UTC 00시, 기본 DRY_RUN=1), `ci.yml`(pytest + gitleaks) | `workflow_dispatch`로 수동 실행 후 성공 로그 확인 | `ci: add daily digest workflow and CI` |
| 9 | README 마무리 | `README.md` (로컬 실행/Secrets/cron 변경/GHA 지터 안내) | 사용자 리뷰 | `docs: add README with setup and ops guide` |

---

## 10. 사용자 확정 사항 (이전 §10 → 답변 반영 v2)

1. 언어/스택: **Python 3.11+** ✅
2. 소스: §4의 **확정 10개**(공식 RSS 없는 Anthropic/Meta/Mistral 드롭, blog.google AI + BAIR 추가). ✅
3. `WINDOW_HOURS=26` ✅ (cron 지터 ~2h 흡수)
4. Claude 모델: **Haiku 4.5** 기본. arXiv 카테고리당 30건 컷으로 입력 토큰 제한. 구조화 출력은
   **tool-use 강제** (`response_format` 미사용). ✅
5. 발송: **DRY_RUN(콘솔)으로만** 끝까지 구현·검증. Slack/Email은 인터페이스 + 모듈 골격만.
   순서는 메일 → 슬랙으로 추후. 7단계 실 발송 검증 생략. ✅
6. 실행 시각: KST 09시(=UTC 00시) ✅
7. 툴 컨텍스트 파일: **CLAUDE.md만** (`@AGENTS.md` 한 줄). 그 외 안 만듦. ✅
8. 저장소: 로컬 git init → 0단계 검증·커밋 → `gh repo create ai-news-digest --private`로 원격 생성 후 푸시.
   푸시 직전 `.gitignore`에 `.env` 포함 / 커밋된 파일에 시크릿 없음 재확인. ✅
9. 0단계 커밋: 검증 후 즉시 진행 ✅

---

## 11. 위험 / 미리 떠올린 함정

- **RSS URL 변경**: 채택 소스 중 일부가 실제로 RSS를 닫았거나 경로가 바뀌었을 수 있음 → 1단계 끝에서 전체 200/파싱 가능 여부를 체크하고 실패 소스를 즉시 보고/교체.
- **published_at 누락/시간대 혼재**: `python-dateutil`로 흡수, tzinfo 없으면 UTC 가정 + 로그 경고.
- **Claude JSON 깨짐**: 재시도 1회 + 폴백(원본 링크 덤프). 파이프라인은 계속 진행.
- **토큰 비용**: 캐시 + 본문 1000자 컷 + 분할 호출 최소화. 일일 호출 1~2회로 설계.
- **GHA cron 지연**: README에 명시. **26h 윈도우는 수십 분~약 2시간의 cron 지터를 흡수하는 정도지,
  하루를 통째로 건너뛴 경우의 항목 손실까지는 보호하지 못한다.** 항목 손실을 회피하려면 추후
  `state/seen.json`을 커밋·푸시하는 방식으로 확장 가능(현재 범위는 시간 윈도우만).
- **개인정보 노출**: 프롬프트 가드 + 발송 직전 정규식 차단.
- **Microsoft Research RSS 간헐 지연**: 1단계 라이브 검증 중 동일 URL이 ~20s timeout과 즉시 200을
  반복하는 분 단위 지연 구간을 보이는 사례 관찰. 3회 재시도(2s/4s backoff)로 스크립트(`check_feeds.py`)는
  안정적으로 통과하나, 동시간대에 `pytest -m network`가 MS Research에서 깨질 수 있다. 재시도는 더 늘리지
  않고 알려진 flake로 인정. 실제 봇 동작은 소스별 격리로 흡수.

---

위 계획에 OK 주면 §9의 0단계부터 시작한다.

---

## 12. 변경 이력
- v2 (이번 갱신):
  - 사용자 확정 결정 반영(WINDOW_HOURS=26, arXiv 30컷, tool-use 강제, DRY_RUN-only 끝까지, gh private repo).
  - 피드 실측: Anthropic/Meta/Mistral 드롭, Stability `?format=rss` 채택, blog.google AI + BAIR 추가 → 최종 10개.
  - §11의 "자동 복구" 문구를 26h 지터 흡수 한정으로 정정.
  - §9에 0.5단계(원격 생성·푸시) 추가, 7단계는 DRY_RUN 갈음으로 변경.
