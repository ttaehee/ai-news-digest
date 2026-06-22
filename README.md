# ai-news-digest

매일 아침 AI 관련 1차 소스를 자동으로 모아 Claude 또는 Gemini로 요약해 한국어 다이제스트로 보내주는 봇.
서버 없이 GitHub Actions에서 돈다.

설계 결정 근거는 [PLAN.md](./PLAN.md), 단계별 진행 상태와 후속 작업 목록은 [STATUS.md](./STATUS.md),
에이전트·기여자용 규칙은 [AGENTS.md](./AGENTS.md) 참고.

## 동작 방식

```
수집 → 정규화 → AI 가공 → 발송
```

1. **수집** — RSS 9개 + arXiv 3개 카테고리(cs.AI/CL/LG) + Hacker News(Algolia) + GeekNews(news.hada.io) = 총 **14개 소스**를 병렬 fetch.
   소스별 격리되어 한 곳이 죽어도 나머지는 진행.
2. **정규화** — 26시간(설정 가능) 내 항목만 통과시키고, HTML/공백 정리.
3. **AI 가공** — 카테고리 5종(Model/Paper/Tool/Misc/Community) 분류 / 0–10 중요도 / 카테고리당 상위 3개 / 한 줄 한국어 요약.
   토큰 한도 넘으면 입력을 절반으로 나눠 호출 후 머지. 모델 호출 실패 2회면 원본 링크 덤프 폴백.
4. **발송** — 콘솔(완전 동작, 기본) · Slack webhook · SMTP 이메일.

소스·LLM 제공자·발송 채널 전부 플러그인 구조다:
`src/ai_news_digest/sources/registry.py` · `providers/{gemini,claude}.py` · `delivery/{console,slack,email_smtp}.py`.

## 빠른 시작 (로컬)

```bash
git clone https://github.com/ttaehee/ai-news-digest.git
cd ai-news-digest

python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install   # 시크릿 커밋 차단 훅 활성화

cp .env.example .env
$EDITOR .env                   # GEMINI_API_KEY 또는 ANTHROPIC_API_KEY 채우기

scripts/run_local.sh           # 기본 DRY_RUN=1 → 콘솔에 다이제스트 출력
```

`GEMINI_API_KEY`는 https://aistudio.google.com 에서 무료 발급된다.

부수 명령:

```bash
.venv/bin/python scripts/check_feeds.py   # 14개 소스 생존 점검
.venv/bin/pytest -q                       # 단위테스트 (네트워크 호출 없음)
.venv/bin/pytest -m network               # 라이브 피드까지 검증 (선택, 가끔 flake)
```

## GitHub Actions로 매일 자동 실행

이 저장소엔 두 워크플로가 들어 있다:

- `.github/workflows/digest.yml` — 매일 한 번 다이제스트 실행.
- `.github/workflows/ci.yml` — push/PR마다 `pytest -q` + gitleaks 시크릿 스캔.

### Secrets 설정

GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**
(또는 `gh secret set NAME` 후 값 입력 — 값이 터미널에 안 찍힌다.)

| Secret | 언제 필요 | 발급처 |
|------|-----------|--------|
| `GEMINI_API_KEY` | 기본 (LLM_PROVIDER=gemini) | https://aistudio.google.com |
| `ANTHROPIC_API_KEY` | LLM_PROVIDER=claude일 때 | https://console.anthropic.com |
| `SLACK_WEBHOOK_URL` | Slack 발송 시 | Slack 앱의 Incoming Webhook |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `MAIL_TO` | 이메일 발송 시 | 사용하는 SMTP 서버 |

기본 안전 경로(`DRY_RUN=true`, 콘솔만)에서는 `GEMINI_API_KEY`만 있으면 충분하다.

### 스케줄 변경

기본 cron: `0 0 * * *` (매일 UTC 00:00 = **KST 09:00**).
`.github/workflows/digest.yml`의 `on.schedule[].cron` 한 줄을 수정한다:

```yaml
on:
  schedule:
    - cron: "0 0 * * *"   # UTC 00:00 = KST 09:00 (기본)
    # 예시:
    # - cron: "30 22 * * *"   # KST 07:30
    # - cron: "0 13 * * 1-5"  # 주중 KST 22:00
```

> **GitHub Actions cron은 정시 실행을 보장하지 않는다.**
> 부하·shared runner 상황에 따라 수십 분에서 수 시간까지 늦어질 수 있다
> ([공식 문서](https://docs.github.com/en/actions/reference/events-that-trigger-workflows#schedule)).
> 이 봇은 `WINDOW_HOURS=26`으로 2시간 오버랩을 둬서 그 정도 지터는 흡수하지만,
> 하루를 통째로 건너뛴 경우의 항목 손실까진 보호하지 않는다.

### 수동 실행

- GitHub UI → **Actions → digest → Run workflow** → `dry_run` 토글.
- 또는 CLI: `gh workflow run digest.yml -f dry_run=true`.

## MCP 서버 (호스트 Claude에서 on-demand 호출)

배치(GHA cron → Slack)와 별개로, 호스트 Claude(Desktop·CLI)에서 직접
다이제스트를 요청할 수 있는 stdio MCP 서버를 함께 제공한다.
**서버는 수집·필터만 하고 요약·분류·점수는 호스트 Claude가 한다** — 그래서
이 경로엔 별도 API 키가 필요 없다 (배치는 기존대로 Gemini로 직접 처리).

도구 한 개: `get_ai_digest(category=None, top_k=3, hours=24) -> str`

| 인자 | 값 | 기본 |
|------|----|------|
| `category` | `Model` / `Paper` / `Tool` / `Misc` / `Community` 또는 한국어 별칭 `모델` / `논문` / `툴` / `기타` / `커뮤니티`. 생략·`전체`·`all`·`""`은 전체. | `None` (전체) |
| `top_k` | 카테고리당 상한 | `3` (1–25로 클램프) |
| `hours` | 시간창(시간) | `24` (1–336으로 클램프) |

### 설치

```bash
.venv/bin/pip install -e ".[mcp]"
```

### Claude Desktop 등록

`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`)
에 추가:

```json
{
  "mcpServers": {
    "ai-news-digest": {
      "command": "/absolute/path/to/ai-news-digest/.venv/bin/python",
      "args": ["-m", "ai_news_digest.mcp_server"]
    }
  }
}
```

`env` 블록 없음 — 이 서버는 API 키가 필요 없다.

### Claude CLI 등록

```bash
claude mcp add ai-news-digest -- \
  /absolute/path/to/ai-news-digest/.venv/bin/python -m ai_news_digest.mcp_server
```

### 사용 예

호스트 Claude와의 대화에서:

> 최근 3일 논문만 10개 정리해줘

→ Claude가 `get_ai_digest(category="논문", top_k=10, hours=72)` 호출
→ 서버가 arXiv 항목을 수집·필터해서 `SYSTEM_PROMPT`와 함께 텍스트로 반환
→ Claude가 그 기준대로 한국어 요약·카테고리 분류·중요도 점수를 매겨 응답.

## 환경변수 레퍼런스

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LLM_PROVIDER` | `gemini` | `gemini` 또는 `claude` |
| `LLM_MODEL` | 제공자 기본 | 모델 ID 오버라이드 (예: `gemini-2.5-flash-lite`, `claude-sonnet-4-6`) |
| `WINDOW_HOURS` | `26` | 수집 시간 윈도우(시간 단위) |
| `DRY_RUN` | `1` | `1`/`true`이면 콘솔만, `0`/`false`이면 실제 발송 |
| `DELIVERY` | (빈값) | `slack` / `email` / 빈값(=콘솔) |
| `GEMINI_API_KEY` | — | LLM_PROVIDER=gemini |
| `ANTHROPIC_API_KEY` | — | LLM_PROVIDER=claude |
| `SLACK_WEBHOOK_URL` | — | DELIVERY=slack |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `MAIL_TO` | — | DELIVERY=email |

## 현재 한계 / 후속 개선

- **발송 채널**: 콘솔·Slack 모두 실 발송 동작. Email은 `SMTPConfig` 검증까지 작성된 스캐폴드 상태로,
  `send()` 호출 시 `NotImplementedError`. 활성화는 후속 작업.
- **Gemini latency**: 기본 모델 `gemini-2.5-flash`는 thinking 활성화로 한 호출에 1~3분 걸린다.
  더 빨리 돌리려면 `LLM_MODEL=gemini-2.5-flash-lite`.
- **Gemini 503 부하 시**: 재시도 사이에 10초 backoff를 둬서 짧은 503 스파이크는 흡수하지만,
  과부하가 길게 이어지면 두 시도 모두 실패해 폴백으로 떨어질 수 있다(실제 관찰됨).
- **Microsoft Research RSS**: 분 단위로 응답이 느려지는 구간이 있음. 3회 재시도로 보통 흡수되지만
  `pytest -m network`에선 가끔 깨지는 알려진 flake.

전체 후속 항목은 [STATUS.md "다음에 개선"](./STATUS.md) 참고.

## 개발 방식

Claude Code와 페어 프로그래밍으로 제작.
AI가 준 코드를 그대로 받지 않고, 소스 검증·구조 설계·버그 수정을 단계마다 직접 판단하며 진행.
자세한 결정 기록은 [PLAN.md](./PLAN.md)와 [STATUS.md](./STATUS.md) 참고.
