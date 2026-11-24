import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = 'BAAI/bge-m3'
MODEL_REVISION = '5617a9f61b028005a4858fdac845db406aefb181'
MODEL_PATH = ROOT / '.runtime/models/bge-m3'
CHROMA_PATH = ROOT / 'rag/chroma'
COLLECTION = 'criteo_knowledge_bge_m3_v1'
MANIFEST = ROOT / 'rag/index_manifest.json'
DOCUMENTS = {
    'table_schema.md': 'schema',
    'metric_definitions.md': 'metric',
    'business_rules.md': 'business_rule',
}


def configure_environment():
    for key, folder in {
        'HF_HOME': '.cache/huggingface', 'TORCH_HOME': '.cache/torch',
        'SENTENCE_TRANSFORMERS_HOME': '.cache/sentence-transformers',
        'TEMP': '.tmp', 'TMP': '.tmp',
    }.items():
        target = ROOT / folder
        target.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(target)
    os.environ['ANONYMIZED_TELEMETRY'] = 'False'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
