from functools import lru_cache

from .settings import MODEL_PATH, configure_environment


@lru_cache(maxsize=1)
def get_model():
    configure_environment()
    if not (MODEL_PATH / 'pytorch_model.bin').is_file():
        raise RuntimeError('Local BGE-M3 model missing; see the RAG section in the project README.md.')
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(4)
    model = SentenceTransformer(str(MODEL_PATH), device='cpu', local_files_only=True,
                                trust_remote_code=False)
    model.max_seq_length = 1536
    return model


def embed(texts):
    model = get_model()
    lengths = [len(model.tokenizer.encode(text, add_special_tokens=True, truncation=False))
               for text in texts]
    if max(lengths, default=0) > model.max_seq_length:
        raise ValueError('A knowledge chunk exceeds 1536 tokens; split the source section before indexing.')
    vectors = model.encode(texts, batch_size=2, normalize_embeddings=True,
                           show_progress_bar=False, convert_to_numpy=True)
    if vectors.shape[1] != 1024:
        raise RuntimeError('Expected 1024-dimensional BGE-M3 embeddings.')
    return vectors.tolist()
