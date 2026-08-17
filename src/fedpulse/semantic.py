"""Provider-independent semantic candidate retrieval.

Embeddings may replace/augment this retriever later, but retrieval never establishes facts.
"""
from __future__ import annotations
import math, re
from collections import Counter

_TOKEN=re.compile(r"[a-z0-9][a-z0-9+.#/-]{1,}")
_STOP={"the","and","for","with","from","that","this","into","services","service","federal","government"}

def tokens(text:str)->list[str]:
    return [x for x in _TOKEN.findall((text or "").lower()) if x not in _STOP]

def event_text(item:dict)->str:
    ids=item.get("identifiers") or {}
    return " ".join(str(x or "") for x in [item.get("title"),item.get("agency"),item.get("stage")," ".join(item.get("reasons") or [])," ".join(v for vals in ids.values() for v in vals)])

def profile_text(profile:dict)->str:
    return " ".join([profile.get("label", ""),*(profile.get("keywords") or []),*(profile.get("geographies") or []),*(profile.get("agencies") or []),*(profile.get("naics") or [])])

def similarity(query:str,document:str)->float:
    q=Counter(tokens(query)); d=Counter(tokens(document))
    if not q or not d:return 0.0
    dot=sum(q[k]*d.get(k,0) for k in q); nq=math.sqrt(sum(v*v for v in q.values())); nd=math.sqrt(sum(v*v for v in d.values()))
    return dot/(nq*nd) if nq and nd else 0.0

def rerank_semantic(items:list[dict],profile:dict,limit:int=100)->list[dict]:
    q=profile_text(profile); out=[]
    for item in items:
        row=dict(item); row["semantic_retrieval_score"]=round(similarity(q,event_text(row)),4); out.append(row)
    out.sort(key=lambda x:(-x["semantic_retrieval_score"],-float(x.get("score") or 0),x.get("event_id") or ""))
    return out[:limit]
