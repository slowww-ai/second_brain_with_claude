"""Rebuild the wiki index from wiki/notes/.

Vector store: LanceDB at wiki/lancedb/ (table `notes`).
Metadata:     SQLite at wiki/index.db (tables `links`, `ingested`).

Embeddings come from Gemini `gemini-embedding-2-preview` via google-genai.
Requires GEMINI_API_KEY in the environment.

Incremental: only re-embeds notes whose mtime changed since the last run.
"""
from __future__ import annotations
import os, re, sqlite3, pathlib, sys, datetime

try:
    from google import genai
except ImportError:
    sys.exit("google-genai not installed. Run: pip install google-genai")

try:
    import lancedb
    import pyarrow as pa
except ImportError:
    sys.exit("lancedb not installed. Run: pip install lancedb pyarrow")

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOTES = ROOT / "wiki" / "notes"
LANCE_DIR = ROOT / "wiki" / "lancedb"
DB = ROOT / "wiki" / "index.db"
MODEL = "gemini-embedding-2-preview"

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"tags:\s*\[(.*?)\]")


def parse(path: pathlib.Path):
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    fm = m.group(1) if m else ""
    body = text[m.end():] if m else text
    tags_m = TAG_RE.search(fm)
    tags = [t.strip().strip("'\"") for t in (tags_m.group(1).split(",") if tags_m else []) if t.strip()]
    links = LINK_RE.findall(body)
    return body, tags, links


def ensure_sqlite(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS links (src TEXT, dst TEXT);
        CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst);
        CREATE TABLE IF NOT EXISTS ingested (
            raw_file TEXT PRIMARY KEY,
            content_hash TEXT,
            ingested_at TEXT,
            produced_notes TEXT
        );
        CREATE TABLE IF NOT EXISTS note_meta (
            id TEXT PRIMARY KEY,
            mtime REAL
        );
    """)


def embed(client, text: str) -> list[float]:
    resp = client.models.embed_content(model=MODEL, contents=text)
    return resp.embeddings[0].values


def open_lance_table(db, dim: int):
    if "notes" in db.table_names():
        return db.open_table("notes")
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("body", pa.string()),
        pa.field("tags", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])
    return db.create_table("notes", schema=schema)


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)

    LANCE_DIR.parent.mkdir(parents=True, exist_ok=True)
    lance = lancedb.connect(str(LANCE_DIR))

    con = sqlite3.connect(DB)
    ensure_sqlite(con)
    cur = con.cursor()

    existing: dict[str, float] = {
        row[0]: row[1] for row in cur.execute("SELECT id, mtime FROM note_meta")
    }
    seen: set[str] = set()
    to_upsert: list[dict] = []

    # Rebuild links from scratch each run.
    cur.execute("DELETE FROM links")

    for p in NOTES.glob("*.md"):
        note_id = p.stem
        seen.add(note_id)
        mtime = p.stat().st_mtime
        body, tags, links = parse(p)
        for dst in links:
            cur.execute("INSERT INTO links(src, dst) VALUES (?, ?)", (note_id, dst))

        if note_id in existing and abs(existing[note_id] - mtime) < 1e-6:
            continue

        vec = embed(client, body[:8000])
        to_upsert.append({
            "id": note_id,
            "body": body,
            "tags": " ".join(tags),
            "vector": vec,
        })

    # Upsert into LanceDB. First-run creates the table with the right dim.
    if to_upsert:
        dim = len(to_upsert[0]["vector"])
        table = open_lance_table(lance, dim)
        ids = [r["id"] for r in to_upsert]
        # Delete existing rows for these ids, then add fresh.
        in_list = ", ".join(f"'{i}'" for i in ids)
        try:
            table.delete(f"id IN ({in_list})")
        except Exception:
            pass
        table.add(to_upsert)
        for r in to_upsert:
            cur.execute(
                "INSERT OR REPLACE INTO note_meta(id, mtime) VALUES (?, ?)",
                (r["id"], NOTES.joinpath(r["id"] + ".md").stat().st_mtime),
            )

    # Remove notes that were deleted from disk.
    deleted_ids = [i for i in existing if i not in seen]
    if deleted_ids and "notes" in lance.table_names():
        table = lance.open_table("notes")
        in_list = ", ".join(f"'{i}'" for i in deleted_ids)
        table.delete(f"id IN ({in_list})")
    for old_id in deleted_ids:
        cur.execute("DELETE FROM note_meta WHERE id=?", (old_id,))

    con.commit()
    con.close()
    print(f"reindex: upserted {len(to_upsert)}, deleted {len(deleted_ids)}")


if __name__ == "__main__":
    main()
