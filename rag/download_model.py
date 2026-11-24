"""Download a pinned official BGE-M3 dense model, with resume and LFS SHA-256 checks."""
import hashlib
import json
import time
from urllib.request import Request, urlopen

from .settings import MODEL_ID, MODEL_PATH, MODEL_REVISION, ROOT

FILES = ['config.json', 'config_sentence_transformers.json', 'modules.json',
         'sentence_bert_config.json', 'special_tokens_map.json', 'tokenizer_config.json',
         'tokenizer.json', 'sentencepiece.bpe.model', '1_Pooling/config.json', 'pytorch_model.bin']


def verify(path, info):
    if not path.exists() or path.stat().st_size != info['size']:
        return False
    if info.get('lfs'):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == info['lfs']['sha256']
    return True


def main():
    cache = ROOT / '.tmp/bge_model_metadata.json'
    if cache.exists():
        metadata = json.loads(cache.read_text(encoding='utf-8-sig'))
    else:
        with urlopen(f'https://huggingface.co/api/models/{MODEL_ID}/revision/{MODEL_REVISION}?blobs=true', timeout=60) as r:
            metadata = json.load(r)
    if metadata['sha'] != MODEL_REVISION:
        raise RuntimeError('Unexpected model revision.')
    information = {item['rfilename']: item for item in metadata['siblings']}
    records = []
    for name in FILES:
        target = MODEL_PATH / name
        target.parent.mkdir(parents=True, exist_ok=True)
        info = information[name]
        partial = target.with_name(target.name + '.part')
        if not verify(target, info):
            for attempt in range(6):
                if verify(partial, info):
                    partial.replace(target)
                    break
                offset = partial.stat().st_size if partial.exists() else 0
                request = Request(f'https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{name}',
                                  headers={'Range': f'bytes={offset}-'} if offset else {})
                try:
                    with urlopen(request, timeout=120) as response:
                        mode = 'ab' if offset and response.status == 206 else 'wb'
                        with partial.open(mode) as output:
                            while block := response.read(1024 * 1024):
                                output.write(block)
                    if verify(partial, info):
                        partial.replace(target)
                        break
                except OSError:
                    if attempt == 5:
                        raise
                    time.sleep(min(2 ** attempt, 10))
            if not verify(target, info):
                raise RuntimeError(f'Model download verification failed: {name}')
        records.append({'file': name, 'bytes': info['size'],
                        'official_sha256': (info.get('lfs') or {}).get('sha256')})
        print(f'Verified {name}', flush=True)
    manifest = {'model': MODEL_ID, 'revision': MODEL_REVISION,
                'source': f'https://huggingface.co/{MODEL_ID}', 'files': records}
    (ROOT / 'rag/model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
