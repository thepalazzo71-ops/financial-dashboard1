import json,sys,numpy as np
D='/tmp/claude-0/-home-user-financial-dashboard1/45600be0-a6c4-5ca9-a40b-02001a7bd8bf/scratchpad/emb/'
rows=json.load(open(D+'dataset.json'))
from sentence_transformers import SentenceTransformer
m=SentenceTransformer('google/embeddinggemma-2',trust_remote_code=True)
texts=[r['text'] if len(r['text'])>10 else '' for r in rows]
idx=[i for i,t in enumerate(texts) if t]
print('embedding',len(idx),'texts',flush=True)
E=np.zeros((len(rows),m.get_sentence_embedding_dimension()),dtype='float32')
vec=m.encode([texts[i] for i in idx],batch_size=32,normalize_embeddings=True,show_progress_bar=False)
E[idx]=vec
np.save(D+'emb.npy',E); print('saved',E.shape)
