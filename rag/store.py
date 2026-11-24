from .settings import CHROMA_PATH, COLLECTION, MODEL_ID, MODEL_REVISION, configure_environment


def collection(create=False):
    configure_environment()
    import chromadb
    from chromadb.config import Settings
    client = chromadb.PersistentClient(path=str(CHROMA_PATH), settings=Settings(anonymized_telemetry=False))
    if create:
        result = client.get_or_create_collection(
            name=COLLECTION, embedding_function=None,
            metadata={'hnsw:space': 'cosine', 'model': MODEL_ID, 'revision': MODEL_REVISION})
    else:
        result = client.get_collection(name=COLLECTION, embedding_function=None)
    if result.metadata.get('revision') != MODEL_REVISION:
        raise RuntimeError('Embedding model revision differs from stored index.')
    return result
