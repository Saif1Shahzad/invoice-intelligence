"""Provider identity is part of the durable job's idempotency key."""
import hashlib,json
from invoice_intelligence.extraction.local import VERSION

def identity(settings):
    if settings.extraction_provider=='groq':
        config={name:getattr(settings,name) for name in ['groq_model','groq_max_tokens','groq_max_pages']}
        from invoice_intelligence.extraction.groq import PROMPT,schema
        config['prompt_schema_sha256']=hashlib.sha256((PROMPT+json.dumps(schema(),sort_keys=True)).encode()).hexdigest()
        return 'groq','groq-vision-v2-'+hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()[:16]
    return 'local',VERSION
