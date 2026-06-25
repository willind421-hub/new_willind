#!/usr/bin/env python
"""검증된 '변수 이름만' 출력기 — dotenv류 파일에서 = 앞(키 이름)만 찍는다.

값(= 뒤)은 절대 출력하지 않는다. 비밀 가드가 이 스크립트 호출만 예외로 허용하므로,
이름 확인이 필요할 때 안전하게 쓴다.

사용: python env_keys.py <파일경로> [이름필터(부분일치, 대소문자무시)]
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: env_keys.py <file> [name_filter]\n")
        return 2
    path = sys.argv[1]
    name_filter = (sys.argv[2].lower() if len(sys.argv) > 2 else "")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except OSError as exc:
        sys.stderr.write(f"cannot read: {type(exc).__name__}\n")
        return 1
    seen = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()  # = 앞만. 값은 버린다.
        # export PREFIX 정리
        if name.lower().startswith("export "):
            name = name[len("export "):].strip()
        if not name:
            continue
        if name_filter and name_filter not in name.lower():
            continue
        if name not in seen:
            seen.append(name)
    for name in seen:
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
