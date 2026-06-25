<div align="center">

# willind

**여러 자동화 프로그램이 한 구조 위에 쌓이도록 설계한 — 에이전트의 척추.**

권한·기억·연결 규칙을 먼저 깔아두고, 실행은 그때그때 가장 적합한 AI 모델에 맡긴다.
특정 모델에 종속되지 않는다 — 이 폴더(= **척추**)를 아무 AI 모델 위에 얹는다.

<br>

![spine](https://img.shields.io/badge/spine-implemented-2ea44f)
![body](https://img.shields.io/badge/body-scaffold-orange)
![model](https://img.shields.io/badge/model-agnostic-blue)
![runtime](https://img.shields.io/badge/runtime-Node%20%2B%20TypeScript-3178c6)

</div>

---

## 한 문장으로

> willind는 **제품이 아니라 척추**다.
> 여러 자동화 프로그램이 *나중에* 한 구조 위에 쌓이도록, **권한·기억·연결 규칙을 먼저 설계**해뒀다.
> 그 중심은 **안전 경계** — 관찰·제안·초안은 그냥 하고, **돈·삭제·외부발송·계정변경** 같은 해를 끼치는 지점에서만 멈춰 묻는다. 에이전트가 네 파일·돈·계정을 함부로 못 건드리게.

여기서 정직하게: 아직 이 척추 위에 얹은 프로그램은 없다. willind가 가진 건 "검증된 확장성"이 아니라 **확장을 염두에 두고 내린 구조 결정들**, 그리고 **실제로 동작하는 권한·안전 경계**(테스트 통과)다. 모델은 소모품, **척추가 정체성**이다.

> **읽기 전에 — 구현 상태 한눈에**
> 이 저장소는 **척추(spine)는 동작하는 구현체**, **몸(body, `willind-mcp/`)은 아직 뼈대(scaffold)** 다.
> 척추의 커널 resolver와 운영 스크립트는 실제로 실행되고 테스트가 통과한다.
> 몸의 MCP 서버는 인증·헬스체크·빈 핸들러까지만 들어있고, 도구·메신저·멀티에이전트는 **직접 채워 넣어야 한다.**
> 자세한 구분은 아래 [구현 상태](#구현-상태) 표 참고.

---

## 두 개의 층

willind는 정적인 "뼈대"와, 이를 실행하는 "몸"으로 나뉜다.

```
┌─────────────────────────────────────────────────────────┐
│  척추 (spine)  ·  파일시스템 기반 에이전트 OS  ── 구현됨   │
│                                                         │
│  registry/      모든 것의 색인 — "움직이기 전에 먼저 읽어라" │
│  core/          커널 resolver · 어댑터 · 보안 가드 · 정책   │
│  capabilities/  능력 계약 (활성 23 + 예약 슬롯 13)        │
│  docs/          큐레이션된 지식베이스 + 권한 매트릭스      │
│  scripts/       실제 운영 구현 45개 (+테스트)            │
└─────────────────────────────────────────────────────────┘
                          ▲  얹는다
                          │
┌─────────────────────────────────────────────────────────┐
│  몸 (body)  ·  willind-mcp — MCP 서버 ── 뼈대(scaffold)   │
│                                                         │
│  ✅ 들어있음:  API 키 인증 · /health · 빈 MCP 핸들러       │
│  ⬜ 비어있음:  도구(0개) · DB 스키마(주석 예시만)          │
│  ⬜ 미구현:    메신저 게이트웨이 · 멀티-LLM 위임 ·         │
│               벡터 메모리 · 멀티에이전트 버스 · 감사 로그   │
└─────────────────────────────────────────────────────────┘
```

> **왜 이렇게 나뉘나.** 척추는 "무엇을 어떻게 결정하는가"의 계약과 판정 로직이고, 몸은 그 결정을 외부 세계에 연결하는 실행 표면이다. 척추는 모델 없이도 그 자체로 읽히고 판정되지만, 몸은 사용자가 자기 도구를 붙여 완성하는 출발점이다.

---

## 할 수 있는 것 — 능력 카탈로그

능력은 전부 **선언적 계약(YAML)** 으로 등록되어 있다. 현재 **활성 계약 23개 + 예약 슬롯 13개**, 총 36개 슬롯이 `capabilities/composed/`에 색인돼 있다.

> 용어: **활성 계약**(`capability.yaml` + 권한등급 + status) = 라우팅 가능한 완성 계약 / **예약 슬롯**(`README.md`만, 본문 미작성) = 자리만 잡힌 향후 능력.

활성 계약 일부:

| 능력 | 하는 일 | 권한등급 |
|------|---------|----------|
| `deep-research-lifecycle` | 리서치를 job id·진행률·취소·결과 라이브러리를 가진 백그라운드 작업으로 | T2 |
| `agent-cost-routing` | "쉬운 건 싼 모델, 어려운 것만 비싼 모델" — 비용 기반 자동 라우팅 | T2 |
| `permission-review` | 로컬 툴·파일·앱 행동의 위험도와 권한 요구를 사전 분류 | policy_gate |
| `runtime-firewall` | 실행 전 프롬프트/응답을 가로채 민감정보 유출·위험 행동 차단 | T3 |
| `untrusted-context-wrapper` | 웹·이메일·툴 출력·외부 스킬을 "명령이 아닌 입력"으로 감싸기 | T1 |
| `swd-file-verification` | "파일 썼다"는 주장을 SHA-256 스냅샷으로 실제 검증 | T2 |
| `prod-data-guard` | 테스트가 실제 운영 데이터(prod DB)에 닿는 걸 훅으로 기계 차단 | T3 |
| `tool-visibility-gate` | 저신뢰 호출자에게 위험한 툴을 실행 전에 숨김/차단 | policy_gate |
| `idea-to-spec-convergence` | 막연한 아이디어를 실행 가능한 프로젝트 명세로 수렴 | T1 |

> 전체 36개(활성 23 + 슬롯 13) 목록은 [`capabilities/composed/`](capabilities/composed/) 참고. 그 외 connector·service·provider 계약이 `registry/`에 등록되어 있다(대부분 contract 슬롯이며 런타임 활성화는 별도).

---

## 설계 철학

- **레지스트리가 척추다.** 파일을 바꾸거나 스킬을 로드하거나 데이터를 옮기기 전에, 에이전트는 먼저 `registry/`를 읽는다 (*register first, move later*).
- **권한은 행동 단위로.** 관찰·제안·초안은 기본 허용. **결제·삭제·외부발송·계정변경** 같은 부수효과만 게이트를 거친다 — *autonomy default allow, until the harm boundary*.
- **외부 채널은 권한이 아니라 입력이다.** Telegram에서 온 메시지든, 웹에서 긁은 텍스트든, 명령으로 신뢰하지 않는다 (프롬프트 인젝션 방어).
- **외부 스킬은 덮어쓰지 않고 감싼다.** 원본은 보존, willind식 어댑터로 래핑 (*wrapped, not rewritten*).
- **특정 AI에 묶이지 않는다.** 어떤 모델이든 이 척추를 얹으면 willind.

---

## 빠른 시작

### 1. 척추 받기

```bash
git clone https://github.com/willind421-hub/new_willind.git
cd new_willind
```

척추(폴더 구조)는 그 자체로 동작한다. AI 모델을 이 폴더에서 켜고 `README.md`와 `registry/_index.yaml`부터 읽히면 willind가 된다.

척추의 판정 로직은 모델 없이도 직접 돌려볼 수 있다:

```bash
# 의도 분류 + 능력/권한 라우팅 판정 (읽기 전용, 실행 안 함)
python3 scripts/operations/skills/resolve-skill-kernel.py "코드 짜줘 버그 고쳐줘"
```

### 2. 몸(MCP 서버) 띄우기 — 선택

> **현재 MCP 서버는 빈 뼈대다.** 띄우면 인증과 `/health`만 응답하고, MCP 도구는 0개다.
> 아래는 그 뼈대를 실행하는 방법이며, 실제 기능은 `src/mcp/server.ts`의 `// TODO`에 도구를 등록하면서 직접 채운다.

```bash
cd willind-mcp
npm install
cp .env.example .env        # 최소: API_KEY 만 채우면 뜬다
npm run dev                 # 개발 모드 (tsx)
# 또는
npm run build && npm start  # 프로덕션
```

확인:

```bash
curl http://127.0.0.1:3100/health
# {"ok":true,"service":"willind-mcp","version":"1.0.0","mcp":"/mcp"}
```

**환경변수 — 코드가 실제로 쓰는 것:**

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `API_KEY` | MCP 서버 인증 키 (`x-api-key` 헤더와 대조). **없으면 모든 요청 401.** | (필수) |
| `MCP_PORT` | MCP 서버 포트 (localhost 바인딩) | `3100` |
| `DB_PATH` | SQLite 경로 | `./willind.db` |

> `.env.example`에는 `DISCORD_*` · `TELEGRAM_BOT_TOKEN` · `WS_PORT` 등도 들어있지만, **현재 코드는 이 값들을 읽지 않는다.** 해당 채널/게이트웨이 기능이 아직 미구현이기 때문이다. 메신저 연동을 직접 구현할 때를 위한 자리표시용으로만 남겨뒀다.

> **DB는 자동 생성된다.** `initDb()`가 첫 실행 때 파일을 만든다. 단, 현재 스키마는 **비어 있다**(테이블 0개, 주석 예시만). 자신의 도구가 쓸 테이블을 `src/db/database.ts`에 정의해야 한다. 저장소에 DB 파일을 커밋할 필요는 없다(`.gitignore` 제외됨).

**실제 스택:** TypeScript · `@modelcontextprotocol/sdk` · better-sqlite3 · express · zod · vitest

---

## 구현 상태

"기능 완비"는 **척추 한정**이다. 몸은 출발점(뼈대)이다.

### 척추 (spine) — ✅ 구현됨

| 구성 | 상태 | 근거 |
|------|------|------|
| `core/kernel/skill_kernel_resolver.py` | ✅ 동작 | 1,257줄, CLI 실행 시 의도 분류→능력/권한 JSON 반환 (읽기 전용) |
| `scripts/operations/` Python 45개 | ✅ 동작 | 약 8,600줄, 검증/계약 테스트 통과 (패키지 루트 + `PYTHONPATH` 기준) |
| `registry/` 계약 56개 | ✅ 존재 | `_index.yaml` 색인 + files/hooks/permissions/providers/services 등 |
| `capabilities/composed/` | ◐ 부분 | 활성 계약 23 + 예약 슬롯 13 |
| `core/security/` (secret_guard 등) | ✅ 동작 | 시크릿 탐지·레드액션 + 자체 테스트 |

### 몸 (body, `willind-mcp/`) — ⬜ 뼈대(scaffold)

| 구성 | 상태 | 비고 |
|------|------|------|
| HTTP 서버 + `/health` | ✅ 동작 | express 5, 127.0.0.1 바인딩 |
| API 키 인증 | ✅ 동작 | `x-api-key` 헤더 대조 |
| `/mcp` 엔드포인트 | ◐ 뼈대 | MCP 핸들러는 붙어 있으나 **등록된 도구 0개** (`// TODO`) |
| DB 스키마 | ⬜ 비어있음 | `initDb()`는 WAL만 켜고 테이블 없음 (주석 예시만) |
| 메신저 게이트웨이 (Telegram/Discord) | ⬜ 미구현 | 코드·의존성 없음 |
| 멀티-LLM 위임 (Codex/Claude/Gemini) | ⬜ 미구현 | — |
| 벡터 메모리 (sqlite-vec) | ⬜ 미구현 | 의존성 없음 |
| 멀티에이전트 메시지 버스 / 감사 로그 | ⬜ 미구현 | — |

> 위 미구현 항목들은 `capabilities/composed/`에 **계약(설계 의도)** 으로는 등록돼 있다. 즉 "어떻게 동작해야 하는가"는 정의돼 있고, 몸 쪽 **실행 코드**가 아직 없는 상태다.

### 의도된 백지 — ⬜ (설계대로)

| 구성 | 상태 | 의도 |
|------|------|------|
| `memory/` | 백지 | 대화로 채워가는 사용자 학습 저장소 |
| `ROLE.md` / `CLAUDE.md` 성격 | 얇은 어댑터만 | 척추로 보내는 진입판. 성격은 처음부터 새로 짠다 |
| 사용자 데이터 | 0 | 쓸수록 willind가 당신을 알아간다 |

---

## 폴더 지도

| 폴더 | 역할 | 상태 |
|------|------|------|
| `registry/` | **척추.** 구조·서비스·스킬·provider의 기준 색인 | ✅ |
| `core/` | 커널 resolver · 공통 어댑터 · 보안 가드 · 정책 | ✅ |
| `capabilities/` | 능력 계약. `composed/`(조합) — 활성 23 + 슬롯 13 | ◐ |
| `workflows/` | 능력을 엮은 절차 | ◐ |
| `willind-mcp/` | MCP 서버 — **뼈대.** 외부 도구·API·메신저 연결 지점 | ⬜ 뼈대 |
| `scripts/` | 운영 도구 스크립트 (+테스트) | ✅ |
| `docs/` | `knowledge/`(지식) · `security/`(권한 매트릭스) | ✅ |
| `memory/` | 사용자 학습 (의도된 백지) | 백지 |

---

## 원칙

- 데이터·능력은 0에서 시작해 필요할 때 하나씩 추가한다.
- 성격은 백지에서 새로 짠다.
- 특정 AI에 묶이지 않는다 — 어떤 모델이든 이 척추를 얹으면 willind.
- **대화로 자라는 willind** — 쓸수록 당신을 알아가고, 능력이 는다.

---

## 다음 단계 (몸 채우기)

뼈대를 실제 willind로 키우려면, 계약은 이미 있으니 **몸 쪽 실행 코드**부터 붙이면 된다. 우선순위 예:

1. **첫 MCP 도구** — `src/mcp/server.ts`의 `// TODO`에 도구 하나 등록(예: `registry/` 조회 도구). 척추를 몸에서 읽는 최소 연결.
2. **DB 스키마** — `src/db/database.ts`에 실제 테이블 정의(권한 감사 로그가 자연스러운 첫 후보).
3. **메신저 게이트웨이** — Telegram/Discord 연동 (`untrusted-context-wrapper` 계약대로 *입력으로만* 취급).
4. **멀티-LLM 위임** — `agent-cost-routing` 계약을 실제 provider 호출에 연결.

---

## 라이선스

[Apache License 2.0](LICENSE) — 상업 이용·수정·배포 모두 자유, **특허·상표 보호**를 포함한다.
자세한 조건은 [LICENSE](LICENSE), 저작권 고지는 [NOTICE](NOTICE)를 참조.

---

<div align="center">
<sub>willind — 모델은 갈아끼우고, 정체성은 남긴다.</sub>
</div>
