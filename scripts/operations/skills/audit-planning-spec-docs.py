from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _files_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    skipped = {".git", ".venv", "node_modules", "__pycache__", "models", "backup"}
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [name for name in dirnames if name not in skipped]
        base = Path(dirpath)
        files.extend(base / name for name in filenames)
    return files


def _plan_artifacts_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    skipped = {".git", ".venv", "node_modules", "__pycache__", "models", "backup"}
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [name for name in dirnames if name not in skipped]
        if "plan.json" in filenames:
            files.append(Path(dirpath) / "plan.json")
    return files


def _classify(path: Path) -> dict[str, str]:
    rel = _rel(path)
    parts = path.relative_to(ROOT).parts
    name = path.name.lower()

    if "artifacts" in parts or "runtime" in parts:
        return {
            "kind": "runtime_artifact",
            "rule": "실행 산출물이다. 설계서처럼 읽지 말고 owner 프로젝트나 runtime 규칙으로 관리한다.",
        }
    if name == "readme.md":
        return {
            "kind": "index_doc",
            "rule": "폴더 안내문이다. 실행 계획이나 설계서가 아니라 안내 색인으로 둔다.",
        }
    if name == "structure_brief.md":
        return {
            "kind": "structure_brief",
            "rule": "프로젝트 구조 브리핑이다. 프로젝트 docs에 유지하되 실행 산출물과 섞지 않는다.",
        }
    if "contracts" in parts or "design-specs" in parts:
        return {
            "kind": "specification",
            "rule": "기능 정의, 계약, 화면/데이터 설계다. planning/specs 또는 docs/contracts 성격으로 관리한다.",
        }
    if "migrations" in parts:
        return {
            "kind": "project_support_file",
            "rule": "문서 폴더 안에 있으나 owner 프로젝트가 참조할 수 있는 보조 파일이다. 이동 전 owner 코드를 확인한다.",
        }
    if "security" in parts:
        return {
            "kind": "security_record",
            "rule": "보안 감사/결정 기록이다. docs/security 또는 planning/decisions 성격으로 유지한다.",
        }
    if "references" in parts:
        return {
            "kind": "project_reference",
            "rule": "구현 판단에 사용한 외부 근거와 참고 자료다. owner 프로젝트의 docs/references 아래에 둔다.",
        }
    if name == "research_notes.md":
        return {
            "kind": "project_reference_legacy",
            "rule": "legacy 이름이다. 내용 확인 후 owner 프로젝트의 references 문서로 이름을 구체화한다.",
        }
    if name in {"architecture.md", "design.md"}:
        return {
            "kind": "specification",
            "rule": "구조/디자인 설계서다. specs 또는 project docs에 유지한다.",
        }
    if "execution" in parts:
        return {
            "kind": "execution_order",
            "rule": "실행 순서와 작업 지시다. planning/execution 아래에 둔다.",
        }
    if "specs" in parts:
        return {
            "kind": "specification",
            "rule": "기능 정의, 계약, 화면/데이터 설계다. planning/specs 아래에 둔다.",
        }
    if "concepts" in parts:
        return {
            "kind": "concept",
            "rule": "초기 아이디어와 제품 방향이다. planning/concepts 아래에 둔다.",
        }
    if "roadmap" in parts:
        return {
            "kind": "roadmap",
            "rule": "장기 단계 지도다. planning/roadmap 아래에 둔다.",
        }
    if "decisions" in parts:
        return {
            "kind": "decision",
            "rule": "되돌리면 안 되는 결정 기록이다. planning/decisions 또는 operations에 둔다.",
        }
    if "docs" in parts and "operations" in parts:
        return {
            "kind": "operation_record",
        }
    if name.endswith("-plan.md"):
        return {
            "kind": "ambiguous_plan_doc",
            "rule": "새 파일에서는 -plan.md보다 execution/spec/roadmap/decision 중 하나로 이름을 정한다.",
        }
    if name == "plan.json":
        return {
            "kind": "runtime_plan_artifact",
            "rule": "실행 산출물 이름이다. 코드가 읽을 수 있으므로 이동·이름 변경 전 owner 코드를 먼저 확인한다.",
        }
    return {
        "kind": "manual_review",
        "rule": "파일 내용이나 owner 코드를 확인한 뒤 concepts/specs/execution/roadmap/decisions 중 하나로 배정한다.",
    }


def main() -> int:
    candidates: list[Path] = []
    candidates.extend(_files_under(ROOT / "docs" / "planning"))
    candidates.extend(_files_under(ROOT / "docs" / "operations" / "willind"))
    projects_root = ROOT / "projects"
    if projects_root.exists():
        for project in projects_root.iterdir():
            if not project.is_dir():
                continue
            candidates.extend(_files_under(project / "docs"))
            candidates.extend(_plan_artifacts_under(project / "artifacts"))

    rows = []
    for path in sorted(set(candidates), key=lambda item: _rel(item).lower()):
        rel = _rel(path)
        if any(part in {".venv", "node_modules", "__pycache__"} for part in path.relative_to(ROOT).parts):
            continue
        if not (
            "/docs/" in f"/{rel}/"
            or "/planning/" in f"/{rel}/"
            or rel.endswith("/plan.json")
            or "/artifacts/" in f"/{rel}/"
        ):
            continue
        info = _classify(path)
        ambiguous = (
            "planning/plans" in rel
            or info["kind"] in {"ambiguous_plan_doc", "runtime_plan_artifact", "manual_review"}
        )
        rows.append(
            {
                "path": rel,
                "kind": info["kind"],
                "ambiguous": ambiguous,
                "rule": info["rule"],
            }
        )

    counts: dict[str, int] = {}
    ambiguous_rows = []
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
        if row["ambiguous"]:
            ambiguous_rows.append(row)

    payload = {
        "ok": True,
        "root": str(ROOT),
        "counts": counts,
        "ambiguous_count": len(ambiguous_rows),
        "ambiguous_samples": ambiguous_rows[:40],
        "rules": {
            "planning_subfolders": ["concepts", "specs", "execution", "roadmap", "decisions"],
            "avoid_new_paths": ["planning/plans", "*-plan.md for implementation work"],
            "runtime_artifacts": "프로젝트 코드가 읽을 수 있으므로 이름 변경보다 contract 문서로 의미를 설명한다.",
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
