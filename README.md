# ai-news-digest

*AI ships every day. The hard part isn't building — it's keeping up.*

AI 모델·논문·도구·커뮤니티 소식을 1차 소스에서 모아 LLM으로 한국어 요약하는 파이프라인.
서버 없이 GitHub Actions에서 매일 돈다. 같은 파이프라인을 MCP 서버로도 호출할 수 있다.

## 동작 방식

```
수집 → 정규화 → AI 가공 → ┬─ 발송 (콘솔·Slack) — GitHub Actions가 매일 실행
                         └─ MCP 서버 — 호스트 Claude가 on-demand로 호출
```

- **수집** — RSS·arXiv·Hacker News·GeekNews 등 14개 소스를 병렬로 fetch. 소스별로 격리되어 일부가 실패해도 나머지는 진행된다.
- **정규화** — 설정한 시간창(기본 26h) 내 항목만 통과, HTML·공백 정리.
- **AI 가공** — 카테고리 5종 분류 · 0–10 중요도 점수로 카테고리당 상위 N개 선별 · 한 줄 한국어 요약. 모델 호출이 실패하면 원본 링크 덤프로 폴백.
- **발송** — 콘솔(기본) · Slack.

## 품질 평가 (eval 하네스)

발송 전 모든 요약을 규칙 기반으로 채점한다. 4개 규칙: 금지어(추상적 hype·filler), 전문용어(안 풀어쓴 용어), 제목 직역 유사도(Jaccard), 길이.

채점 기준은 `eval/constants.py`에 있고 LLM 프롬프트가 이를 import한다.

통과율이 매 발송마다 출력되고(예: `📊 요약 품질: 2/3 통과 (67%)`), 70% 미만이면 경고로 바뀐다.

## MCP 서버

호스트 Claude에서 직접 다이제스트를 요청할 수 있는 stdio MCP 서버. 수집·필터만 하고 요약·분류·점수는 호스트 Claude가 맡으므로 API 키가 필요 없다.

도구 한 개: `get_ai_digest(category=None, top_k=3, hours=24)`

> "최근 3일 논문만 10개 정리해줘" → `get_ai_digest(category="논문", top_k=10, hours=72)` → 서버가 수집·필터한 항목을 반환하면 Claude가 요약·분류한다.

<details>
<summary>인자 상세</summary>

| 인자 | 값 | 기본 |
|------|----|------|
| `category` | `Model` / `Paper` / `Tool` / `Misc` / `Community` (한국어 별칭 가능). 생략 시 전체. | 전체 |
| `top_k` | 카테고리당 상한 (1–25) | `3` |
| `hours` | 시간창 (1–336) | `24` |

</details>

## Claude Code 플러그인

```bash
claude plugin marketplace add ttaehee/ai-news-digest
claude plugin install ai-news-digest
```

Claude Code가 MCP 서버를 자동 등록한다. Python 3.12+ 필요. 첫 호출 때 플러그인 전용 venv에 의존성을 한 번 설치한다.

<details>
<summary>수동 등록</summary>

**Claude Desktop** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ai-news-digest": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "ai_news_digest.mcp_server"]
    }
  }
}
```

**Claude CLI**:

```bash
claude mcp add ai-news-digest -- /absolute/path/to/.venv/bin/python -m ai_news_digest.mcp_server
```

`.venv/bin/pip install -e ".[mcp]"`로 의존성 설치.

</details>

## 로컬 실행

파이프라인을 로컬에서 한 번 실행해 다이제스트를 콘솔에 출력한다.

```bash
git clone https://github.com/ttaehee/ai-news-digest.git
cd ai-news-digest

python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install

cp .env.example .env
$EDITOR .env          # GEMINI_API_KEY

scripts/run_local.sh  # DRY_RUN=1, 콘솔 출력
```

`GEMINI_API_KEY`는 https://aistudio.google.com 에서 무료 발급된다.

## GitHub Actions

`digest.yml`이 매일 다이제스트를 실행하고, `ci.yml`이 push/PR마다 `pytest`와 `gitleaks`를 돈다. 기본 cron은 `0 0 * * *` (KST 09:00).

<details>
<summary>Secrets · 스케줄 · 수동 실행</summary>

**Secrets** (Settings → Secrets and variables → Actions):

| Secret | 언제 |
|------|------|
| `GEMINI_API_KEY` | 기본 |
| `ANTHROPIC_API_KEY` | `LLM_PROVIDER=claude` |
| `SLACK_WEBHOOK_URL` | Slack 발송 |

`DRY_RUN=true`면 `GEMINI_API_KEY`만 있으면 된다.

**스케줄** — `digest.yml`의 `cron`을 수정. GitHub Actions cron은 정시를 보장하지 않아 수십 분~수 시간 지연될 수 있다([문서](https://docs.github.com/en/actions/reference/events-that-trigger-workflows#schedule)). `WINDOW_HOURS=26` 오버랩으로 그 정도 지터는 흡수한다.

**수동 실행** — Actions → digest → Run workflow, 또는 `gh workflow run digest.yml -f dry_run=true`.

</details>

## 환경변수

| 변수 | 기본 | 설명 |
|------|------|------|
| `LLM_PROVIDER` | `gemini` | `gemini` 또는 `claude` |
| `LLM_MODEL` | 제공자 기본 | 모델 ID 오버라이드 |
| `WINDOW_HOURS` | `26` | 수집 시간창 |
| `DRY_RUN` | `1` | `1`=콘솔, `0`=실제 발송 |
| `DELIVERY` | (빈값) | `slack` / 빈값(콘솔) |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | — | provider별 |
| `SLACK_WEBHOOK_URL` | — | Slack 발송 시 |

## 현재 한계

- 이메일 발송은 미구현(인터페이스만 있음). 콘솔·Slack은 동작.
- Gemini 기본 모델은 한 호출에 1~3분. `LLM_MODEL=gemini-2.5-flash-lite`로 단축 가능. 503 과부하가 길어지면 폴백으로 떨어진다.

## 문서

[PLAN.md](./PLAN.md) · [STATUS.md](./STATUS.md) · [AGENTS.md](./AGENTS.md)
