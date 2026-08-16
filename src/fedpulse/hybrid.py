"""Hybrid semantic + AI comparison layer for ranked FedPulse candidates."""
from __future__ import annotations
from .ai_reranker import rerank
from .opportunities import load_profile
from .semantic import rerank_semantic

def compare_rankings(items:list[dict],profile_name:str="default",semantic_limit:int=100,ai_limit:int=30,transport=None)->dict:
    profile=load_profile(profile_name); deterministic=[dict(x) for x in items]; semantic=rerank_semantic(deterministic,profile,semantic_limit); shortlist=semantic[:ai_limit]
    hybrid=rerank(shortlist,profile_name,profile,**({"transport":transport} if transport else {}))
    det_rank={x.get("event_id"):i+1 for i,x in enumerate(deterministic)}; sem_rank={x.get("event_id"):i+1 for i,x in enumerate(semantic)}; hyb_rank={x.get("event_id"):i+1 for i,x in enumerate(hybrid)}
    comparisons=[]
    for row in hybrid:
        event_id=row.get("event_id"); comparisons.append({"event_id":event_id,"deterministic_rank":det_rank.get(event_id),"semantic_rank":sem_rank.get(event_id),"hybrid_rank":hyb_rank.get(event_id),"deterministic_score":row.get("score"),"semantic_score":row.get("semantic_retrieval_score"),"hybrid_score":row.get("hybrid_score",row.get("score")),"ai_adjustment":row.get("ai_adjustment",0),"ai_status":row.get("ai",{}).get("status","disabled")})
    return {"profile":profile_name,"deterministic_count":len(deterministic),"semantic_count":len(semantic),"ai_candidate_count":len(shortlist),"hybrid":hybrid,"comparison":comparisons}
