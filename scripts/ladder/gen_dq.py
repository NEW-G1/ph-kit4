"""레이어 게이트 SQL 생성 (결정 60).

docs/requirements/<마트>_checks/l3/*.sql(위반 행을 돌려주는 쿼리)을 읽어 층마다 게이트 파일
dags/sql/dq/<gate task>.sql을 만든다. 검사마다 `ASSERT NOT EXISTS (...) AS '[C-xx] <rule>'`로 감싸고,
맨 앞에 강제 실패 파라미터 검사(design_principles.md §4)를 둔다.
builder는 dags/sql/dq/에 쓰지 않는다. L3는 이 생성 결과와 파일 해시가 같은지 본다.

  python scripts/ladder/gen_dq.py --mart <마트> [--root <저장소>] [--check]
  --check: 파일을 쓰지 않고 생성 결과와 다르면 종료 코드 1
"""
import argparse
import hashlib
import sys
from pathlib import Path

import common

HEAD = ("-- 자동 생성: scripts/ladder/gen_dq.py (결정 60). 직접 고치지 않는다.\n"
        "-- 원본: docs/requirements/{mart}_checks/l3/\n"
        "ASSERT NOT {{{{ params.force_fail }}}} AS '[DQ-FORCE] 강제 실패 파라미터가 참';\n")


def message(text):
    """ASSERT 메시지 문자열. 렌더링·문자열을 깨는 글자는 쓰지 않는다 (sql_rules.md §1 주의)."""
    if any(c in text for c in "{}'\\\n"):
        raise ValueError(f"rule 문장에 쓸 수 없는 글자가 있음: {text!r}")
    return text


def generate(paths, contract):
    """{게이트 파일 경로: 내용}. l3 형식 오류나 연결 오류는 ValueError."""
    tasks = {t["id"]: t for t in contract["dag"]["tasks"]}
    rules = {c["id"]: c["rule"] for group in contract["checks"].values() for c in group}
    by_layer = {}
    for check_id, header, body in common.load_checks(paths, "l3"):
        task = tasks.get(header["task"])
        if task is None or task["kind"] != "load":
            raise ValueError(f"l3/{check_id}.sql: task {header['task']!r}가 contract의 load task가 아님")
        if check_id not in rules:
            raise ValueError(f"l3/{check_id}.sql: contract checks에 없는 id")
        by_layer.setdefault(task["layer"], []).append((check_id, body))
    out = {}
    for gate in (t for t in contract["dag"]["tasks"] if t["kind"] == "gate"):
        parts = [HEAD.format(mart=paths.mart)]
        for check_id, body in sorted(by_layer.get(gate["layer"], [])):
            parts.append(f"\nASSERT NOT EXISTS (\n{body}\n) AS '[{check_id}] {message(rules[check_id])}';\n")
        out[paths.task_sql(gate)] = "".join(parts)
    return out


def sha256_text(text):
    """줄바꿈(CRLF/LF)만 맞춘 sha256. 파일은 bytes로 넘긴다. 인코딩이 깨진 파일도 디코딩하지 않고 "다름"이 된다
    (3-3 스모크 2차: CP949로 덧붙인 게이트 파일)."""
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="l3 검사로 레이어 게이트 SQL 생성 (결정 60)")
    p.add_argument("--mart", required=True)
    p.add_argument("--root", default=str(common.PROJECT))
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    paths = common.Paths(args.root, args.mart)
    try:
        files = generate(paths, common.load_contract(paths))
    except (ValueError, common.LadderError) as e:
        print(f"생성하지 않음: {e}", file=sys.stderr)
        return 2
    differ = []
    for path, text in files.items():
        current = path.read_bytes() if path.exists() else None
        if current is not None and sha256_text(current) == sha256_text(text):
            continue
        differ.append(path)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    for path in differ:
        print(("다름: " if args.check else "생성: ") + path.relative_to(paths.root).as_posix())
    return 1 if args.check and differ else 0


if __name__ == "__main__":
    sys.exit(main())
