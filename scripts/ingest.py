"""Helpers for the ingest workflow.

Usage:
    python scripts/ingest.py stamp <file>               # add frontmatter if missing
    python scripts/ingest.py list-new                   # list raw/ files not yet ingested
    python scripts/ingest.py record <raw> <note1,note2> # mark a raw file as ingested
    python scripts/ingest.py hash <file>                # print content hash

The ledger lives in wiki/index.db -> `ingested` table. A raw file is considered
"new" if its content hash isn't in the ledger, so renames and edits are handled
correctly.
"""
from __future__ import annotations
import sys, re, datetime, pathlib, hashlib, sqlite3

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "wiki" / "raw"
DB = ROOT / "wiki" / "index.db"


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s[:50] or "untitled"


def content_hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS ingested (
            raw_file TEXT PRIMARY KEY,
            content_hash TEXT,
            ingested_at TEXT,
            produced_notes TEXT
        );
    """)
    return con


def stamp(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        print(f"already stamped: {path.name}")
        return
    today = datetime.date.today().isoformat()
    slug = slugify(path.stem)
    fm = (
        f"---\n"
        f"id: {today}-{slug}\n"
        f"date: {today}\n"
        f"source: unknown\n"
        f"status: draft\n"
        f"---\n\n"
    )
    path.write_text(fm + text, encoding="utf-8")
    print(f"stamped: {path.name}")


def list_new() -> None:
    con = connect()
    ledger: dict[str, str] = {
        row[0]: row[1] for row in con.execute("SELECT raw_file, content_hash FROM ingested")
    }
    for r in sorted(RAW.glob("*")):
        if r.is_dir() or r.name.startswith("."):
            continue
        # Only text markdown files are directly ingestible; images/pdfs need
        # a companion .md (handled by /ingest).
        if r.suffix.lower() != ".md":
            companion = r.with_suffix(r.suffix + ".md")
            sibling = r.with_suffix(".md")
            if not companion.exists() and not sibling.exists():
                print(f"{r.name}  (needs companion .md)")
            continue
        h = content_hash(r)
        if ledger.get(r.name) != h:
            status = "new" if r.name not in ledger else "changed"
            print(f"{r.name}  ({status})")


def record(raw_name: str, produced: str) -> None:
    path = RAW / raw_name
    if not path.exists():
        sys.exit(f"no such raw file: {raw_name}")
    con = connect()
    con.execute(
        "INSERT OR REPLACE INTO ingested(raw_file, content_hash, ingested_at, produced_notes) "
        "VALUES (?, ?, ?, ?)",
        (raw_name, content_hash(path), datetime.datetime.now().isoformat(timespec="seconds"), produced),
    )
    con.commit()
    con.close()
    print(f"recorded: {raw_name} -> {produced}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__); return 1
    cmd = sys.argv[1]
    if cmd == "stamp":
        for p in sys.argv[2:]:
            stamp(pathlib.Path(p))
    elif cmd == "list-new":
        list_new()
    elif cmd == "record":
        record(sys.argv[2], sys.argv[3])
    elif cmd == "hash":
        print(content_hash(pathlib.Path(sys.argv[2])))
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
