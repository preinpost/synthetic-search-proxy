# open-webui-search-proxy

Open WebUI의 **External Web Search**를 [Synthetic](https://synthetic.new) 웹 검색 API에 연결하는 얇은 어댑터입니다.

Open WebUI는 `{"query", "count"}`를 POST하고 `[{"link","title","snippet"}]` 배열을 기대합니다.
Synthetic은 `{"results":[{"url","title","text","published"}]}`를 반환합니다. 이 프록시가 둘 사이를 변환합니다.

## API

```
POST /search
Authorization: Bearer <PROXY_KEY>
{ "query": "검색어", "count": 5 }

-> [ { "link": "...", "title": "...", "snippet": "..." }, ... ]
```

`GET /health` → `{"status":"ok"}`

## 실행

### Docker

```bash
docker run -d --name search-proxy -p 8000:8000 \
  -e SYNTHETIC_API_KEY=sk-... \
  -e PROXY_KEY=my-secret \
  ghcr.io/<owner>/open-webui-search-proxy:latest
```

### docker compose

```bash
cp .env.example .env            # 값 채우기
docker compose up -d            # 독립 실행 (compose.yaml)
docker compose -f compose.webui.yaml up -d   # Open WebUI 동반 실행
```

### 로컬 (개발, uv)

```bash
uv sync
SYNTHETIC_API_KEY=sk-... PROXY_KEY=my-secret \
  uv run uvicorn app.main:app --reload --port 8000
```

의존성은 `pyproject.toml` + `uv.lock`으로 관리합니다. 추가 시 `uv add <pkg>`.

## 환경변수

| 변수 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `SYNTHETIC_API_KEY` | ✅ | — | Synthetic API 키 |
| `PROXY_KEY` | | (빈값=인증 끔) | Open WebUI가 보낼 Bearer 토큰 |
| `SYNTHETIC_URL` | | `https://api.synthetic.new/v2/search` | 업스트림 URL |
| `REQUEST_TIMEOUT` | | `20` | 업스트림 타임아웃(초) |
| `SNIPPET_MAX_CHARS` | | `2000` | snippet당 최대 글자수(0=무제한). Synthetic이 `text`에 페이지 본문 전체를 주므로 잘라서 응답 비대화 방지 |
| `PORT` | | `8000` | 리슨 포트 |
| `LOG_LEVEL` | | `INFO` | 로그 레벨 |

## Open WebUI 설정

Admin Panel → Settings → Web Search

1. Web Search **On**
2. Web Search Engine = **`external`**
3. External Web Search URL = `http://<proxy-host>:8000/search`
4. External Web Search API Key = `PROXY_KEY` 값

## Claude Code / MCP (웹서치 도구로)

서드파티 백엔드(Synthetic 등)의 Claude Code에선 내장 WebSearch가 안 뜬다
(Anthropic 서버사이드 `web_search_*`에 하드코딩 → 백엔드 교체 불가). 이때 이 프록시를
**MCP `web_search` 도구**로 붙이면 검색이 부활한다. MCP는 클라이언트사이드라 LLM 백엔드 무관.

같은 GHCR 이미지를 stdio로 실행 — 각자 본인 키 사용:

```bash
claude mcp add synthetic-search \
  -e SYNTHETIC_API_KEY=$SYNTHETIC_API_KEY \
  -- docker run -i --rm -e SYNTHETIC_API_KEY \
       ghcr.io/preinpost/synthetic-search-proxy:latest python -m app.mcp_server
```

- 로컬(레포 클론): `... -- uv run --directory /path/to/repo python -m app.mcp_server`
- HTTP 모드(팀 공유): 컨테이너를 `MCP_TRANSPORT=http MCP_PORT=9000`으로 띄우고
  `claude mcp add --transport http synthetic-search http://<host>:9000/mcp`

도구: `web_search(query, max_results=5)` → 제목·URL·스니펫(`SNIPPET_MAX_CHARS`로 절단). 전문은 클라이언트 fetch로.

## 빌드 / 배포 (자동 version bump)

`.github/workflows/docker-build.yml` 가 멀티아치(amd64/arm64) 이미지를
`ghcr.io/<owner>/open-webui-search-proxy`로 빌드·푸시합니다.

- **PR**: 빌드만 (푸시 X)
- **main push**: [conventional commits](https://www.conventionalcommits.org)로 다음 semver를 자동 계산
  → 이미지 `:<버전>` + `:latest` + `:sha-xxxx` 푸시 → git 태그 `v<버전>` + GitHub Release 생성

| 커밋 메시지 | 버전 변화 |
|---|---|
| `fix: ...` / 기타 | patch (`1.0.0` → `1.0.1`) |
| `feat: ...` | minor (`1.0.0` → `1.1.0`) |
| `feat!: ...` 또는 본문에 `BREAKING CHANGE:` | major (`1.0.0` → `2.0.0`) |

기본값(`default_bump: patch`)이라 main에 push할 때마다 최소 patch가 올라갑니다.
"feat/fix 커밋이 있을 때만 릴리스"로 바꾸려면 워크플로의 `default_bump: patch` → `default_bump: false`.

> 첫 릴리스 버전을 `pyproject.toml`의 `1.0.0`에 맞추려면 한 번만 시드 태그를 만들어 두세요:
> `git tag v1.0.0 && git push origin v1.0.0` → 이후 push는 `v1.0.1`부터.
> (태그가 하나도 없으면 액션이 `v0.1.0`/`v0.0.1`부터 시작합니다.)

테스트 빠른 확인:

```bash
curl -s localhost:8000/search \
  -H 'Authorization: Bearer my-secret' \
  -H 'Content-Type: application/json' \
  -d '{"query":"python requests docs","count":3}' | jq
```
