import os, unittest
from unittest.mock import patch
from fedpulse.ai_reranker import Budget,evidence_packet,rerank
from fedpulse.semantic import similarity,rerank_semantic

PROFILE={"label":"Seattle construction","keywords":["roofing","construction"],"geographies":["seattle","washington"],"naics":["238160"]}
ITEM={"event_id":"x","source":"sam","kind":"contract_opportunity","stage":"Sources Sought","title":"Roof replacement","agency":"VA","event_date":"2026-08-16","amount":500000,"currency":"USD","official_url":"https://sam.gov/x","days_to_close":20,"identifiers":{"naics":["238160"]},"score":80,"score_components":{"relevance":40},"edge":"early","reasons":["NAICS: 238160"]}
class HybridTests(unittest.TestCase):
 def test_packet_has_evidence_ids(self):
  p=evidence_packet(ITEM,"default",PROFILE);self.assertEqual(p["event_id"],"x");self.assertTrue(any(x["evidence_id"]=="fact:identifiers" for x in p["evidence"]))
 def test_disabled_is_exact_fallback(self):
  with patch.dict(os.environ,{"FEDPULSE_AI_ENABLED":"0"}):self.assertEqual(rerank([ITEM],"default",PROFILE),[ITEM])
 def test_analyst_and_skeptic_are_bounded(self):
  def transport(role,packet,prior):
   if role=="analyst":return {"semantic_relevance":"yes","commercial_fit":"high","actionability":"now","hidden_gem":"yes","evidence_sufficiency":"sufficient","reasons":[{"text":"direct NAICS fit","evidence_ids":["fact:identifiers"]}],"disqualifiers":[],"recommended_adjustment":20}
   return {"verdict":"reject","issues":[{"type":"fit","text":"not enough evidence","evidence_ids":["fact:title"]}],"adjustment":-20}
  with patch.dict(os.environ,{"FEDPULSE_AI_ENABLED":"1"}):
   row=rerank([ITEM],"default",PROFILE,transport=transport,budget=Budget(1,1))[0];self.assertTrue(row["ai"]["rejected"]);self.assertLessEqual(row["ai_adjustment"],-20)
 def test_bad_evidence_reference_falls_back(self):
  def transport(role,packet,prior):return {"semantic_relevance":"yes","commercial_fit":"high","actionability":"now","hidden_gem":"no","evidence_sufficiency":"sufficient","reasons":[{"text":"invented","evidence_ids":["web:made-up"]}],"disqualifiers":[],"recommended_adjustment":20}
  with patch.dict(os.environ,{"FEDPULSE_AI_ENABLED":"1"}):
   row=rerank([ITEM],"default",PROFILE,transport=transport,budget=Budget(1,0))[0];self.assertEqual(row["hybrid_score"],80);self.assertEqual(row["ai"]["status"],"fallback")
 def test_semantic_retrieval_prefers_profile_language(self):
  items=[ITEM,{**ITEM,"event_id":"y","title":"Office furniture subscription","identifiers":{},"score":90,"reasons":[]}];ranked=rerank_semantic(items,PROFILE);self.assertEqual(ranked[0]["event_id"],"x");self.assertGreater(similarity("roof construction","roof construction seattle"),0)
if __name__=="__main__":unittest.main()
