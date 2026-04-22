"""Semantic search over the wiki.

Vector search uses LanceDB at wiki/lancedb/ (table `notes`).
Backlinks and metadata live in wiki/index.db.

Usage:
    python scripts/search.py "<query>"           # semantic search
    python scripts/search.py --tag <tag>         # substring filter on tags
    python scripts/search.py --backlinks <note>  # notes linking to <note>

Requires GEMINI_API_KEY.
"""
from __future__ import annotations
import os, sys, sqlite3, pathlib

try:
    from google import genai
except ImportError:
    sys.exit("google-genai not installed. Run: pip install google-genai")

try:
    import lancedb
except ImportError:
    sys.exit("lancedb not installed. Run: pip install lancedb pyarrow")

ROOT = pathlib.Path(__file__).resolve().parent.parent
LANCE_DIR = ROOT / "wiki" / "lancedb"
DB = ROOT / "wiki" / "index.db"
MODEL = "gemini-embedding-2-preview"


def embed_query(q: str) -> list[float]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY not set")
    client = genai.Client(api_key=key)
    resp = client.models.embed_content(model=MODEL, contents=q)
    return resp.embeddings[0].values


def semantic(query: str, limit: int = 10) -> None:
    qvec = embed_query(query)
    db = lancedb.connect(str(LANCE_DIR))
    if "notes" not in db.table_names():
        print("no notes indexed yet — run scripts/reindex.py")
        return
    table = db.open_table("notes")
    results = table.search(qvec).limit(limit).to_list()
    for r in results:
        score = r.get("_distance", 0.0)
        snippet = (r.get("body") or "").strip().replace("\n", " ")[:160]
        print(f"{score:.3f}  {r['id']}\n  {snippet}\n")


def by_tag(tag: str) -> None:
    db = lancedb.connect(str(LANCE_DIR))
    if "notes" not in db.table_names():
        return
    table = db.open_table("notes")
    for r in table.search().where(f"tags LIKE '%{tag}%'").limit(1000).to_list():
        print(r["id"])


def backlinks(note: str) -> None:
    con = sqlite3.connect(DB)
    for row in con.execute("SELECT src FROM links WHERE dst = ?", (note,)):
        print(row[0])


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__); return 1
    if sys.argv[1] == "--tag":
        by_tag(sys.argv[2])
    elif sys.argv[1] == "--backlinks":
        backlinks(sys.argv[2])
    else:
        semantic(" ".join(sys.argv[1:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
