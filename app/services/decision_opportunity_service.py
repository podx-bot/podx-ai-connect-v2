"""PODX Decision & Opportunity Intelligence.

Common action layer for products, jobs, services and local opportunities.
It optimizes for useful economic outcomes: EARN, SAVE, BUY_SMART, USE_BETTER.
Recommendations remain explainable and user-controlled; no forced action.
"""
from __future__ import annotations
from typing import Any, Dict, List

class DecisionOpportunityService:
    OUTCOMES=("EARN","SAVE","BUY_SMART","USE_BETTER")

    def decide(self,intent:Dict[str,Any],options:List[Dict[str,Any]])->Dict[str,Any]:
        goal=str(intent.get("goal") or "").upper()
        if goal not in self.OUTCOMES: goal=self._infer_goal(intent)
        scored=[]
        for option in options:
            item=dict(option);item["decision_score"],item["reasons"]=self._score(goal,item,intent);scored.append(item)
        scored.sort(key=lambda x:-x["decision_score"])
        best=scored[0] if scored else None
        return {"goal":goal,"best":best,"alternatives":scored[1:4],"action":self._action(best,goal),"user_choice_required":True}

    def proactive_opportunities(self,profile:Dict[str,Any],candidates:List[Dict[str,Any]])->List[Dict[str,Any]]:
        if not profile.get("opportunity_opt_in",False): return []
        result=[]
        for c in candidates:
            relevance=float(c.get("relevance") or 0);confidence=float(c.get("confidence") or 0)
            if relevance>=0.75 and confidence>=0.65:
                x=dict(c);x["why_notified"]=c.get("reason") or "Matches your saved need, skill or price target";result.append(x)
        return sorted(result,key=lambda x:-(float(x.get("relevance") or 0)*float(x.get("confidence") or 0)))[:5]

    @staticmethod
    def _infer_goal(i:Dict[str,Any])->str:
        kind=str(i.get("intent") or i.get("type") or "").lower()
        if any(x in kind for x in ("job","work","sell","earn")):return "EARN"
        if any(x in kind for x in ("save","cheaper","price","discount")):return "SAVE"
        if any(x in kind for x in ("use","repair","reuse","existing")):return "USE_BETTER"
        return "BUY_SMART"

    @staticmethod
    def _score(goal:str,o:Dict[str,Any],i:Dict[str,Any]):
        score=50.0;reasons=[]
        for key,points,label in (("verified",10,"verified"),("nearby",8,"nearby"),("quality_ok",10,"quality fit"),("warranty",6,"warranty"),("service_available",6,"service")):
            if o.get(key):score+=points;reasons.append(label)
        if goal=="EARN" and o.get("earning_amount") is not None:score+=10;reasons.append("earning opportunity")
        if goal=="SAVE" and o.get("saving_amount") is not None:score+=10;reasons.append("saves money")
        if goal=="BUY_SMART" and o.get("best_value"):score+=10;reasons.append("best value")
        if goal=="USE_BETTER" and o.get("avoids_new_purchase"):score+=15;reasons.append("avoids unnecessary purchase")
        return min(100.0,score),reasons

    @staticmethod
    def _action(best:Dict[str,Any]|None,goal:str)->str:
        if not best:return "SEARCH_MORE"
        if best.get("avoid_purchase"):return "KEEP_OR_REUSE"
        return {"EARN":"VIEW_OPPORTUNITY","SAVE":"CHOOSE_SAVING_OPTION","BUY_SMART":"REVIEW_BEST_VALUE","USE_BETTER":"USE_EXISTING_BETTER"}.get(goal,"REVIEW")
