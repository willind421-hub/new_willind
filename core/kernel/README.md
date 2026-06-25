# Willind Skill Kernel

`core/kernel`은 실행 엔진이 아니라 판단 흐름의 계약이다. 실제 실행 코드는 각 프로젝트, tool slot, connector, runtime이 맡고, kernel은 입력이 들어왔을 때 어떤 순서로 능력, provider, 권한, 기록을 연결해야 하는지 정의한다.

기준 문서:


핵심 원칙:

1. `registry`가 Willind의 척추다.
2. `core/kernel`은 입력 -> 판단 -> capability 선택 -> provider 선택 -> permission 확인 -> 실행/응답 -> 기록 흐름을 정의한다.
3. 외부 스킬 원본은 `capabilities/imported`에 보관하고 live behavior로 직접 연결하지 않는다.
4. 실제 Willind 능력은 `capabilities/composed/<capability>/capability.yaml`로 정의한다.
5. provider는 교체 가능한 실행 엔진이다. Codex, Claude, Gemini, local 모델이 바뀌어도 capability 계약은 유지되어야 한다.
6. 관찰, 제안, 초안은 자동 가능하다. 실행, 삭제, 외부 전송, 결제, 계정 변경은 Permission Gate를 통과한다.

대표 계약:

- `kernel-routing.yaml`: kernel 판단 흐름과 읽어야 할 registry 파일.

