import json
from datetime import datetime, timezone

from .chunks import document_hashes, load_chunks
from .embedding import embed
from .settings import COLLECTION, MANIFEST, MODEL_ID, MODEL_REVISION
from .store import collection


def main():
    before = document_hashes()
    chunks = load_chunks()
    vectors = embed([chunk['text'] for chunk in chunks])
    if document_hashes() != before:
        raise RuntimeError('Knowledge changed during indexing; rerun the build.')
    target = collection(create=True)
    target.upsert(ids=[c['id'] for c in chunks], documents=[c['text'] for c in chunks],
                  metadatas=[c['metadata'] for c in chunks], embeddings=vectors)
    active = {c['id'] for c in chunks}
    stale = [identifier for identifier in target.get(include=[])['ids'] if identifier not in active]
    if stale:
        target.delete(ids=stale)
    manifest = dict(model=MODEL_ID, revision=MODEL_REVISION, dimensions=1024,
                    collection=COLLECTION, chunks=len(chunks), document_sha256=before,
                    built_at=datetime.now(timezone.utc).isoformat())
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
