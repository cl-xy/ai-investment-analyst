"""
LLM-as-judge evaluation — uses Llama-8B to score analysis outputs.

Scores on 3 dimensions:
- Citation support: Are claims backed by referenced sources?
- Balanced reasoning: Does the analysis present bull/bear cases?
- Risk disclosure: Are risks and limitations clearly stated?

Each dimension scored 1-5. Run on golden test set only.
"""
import os
import json
from typing import Any
from functools import cache

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


class JudgeScore(BaseModel):
    citation_support: int = Field(ge=1, le=5, description="Are claims backed by cited sources?")
    balanced_reasoning: int = Field(ge=1, le=5, description="Does analysis present both sides?")
    risk_disclosure: int = Field(ge=1, le=5, description="Are risks and data gaps noted?")
    overall: float = Field(ge=1.0, le=5.0, description="Weighted average")
    rationale: str = Field(description="Brief explanation of scoring")


JUDGE_PROMPT = """You are evaluating the quality of a stock analysis output.
Score the following analysis on three dimensions (1-5 each):

1. Citation Support: Are claims backed by specific data sources? 5 = every claim cites a source, 1 = no citations.
2. Balanced Reasoning: Does the analysis present bull AND bear cases fairly? 5 = both sides equally covered, 1 = completely one-sided.
3. Risk Disclosure: Are risks, limitations, and data gaps clearly stated? 5 = comprehensive risk section, 1 = no mention of risks.

Analysis to evaluate:
```json
{analysis}
```

Respond with ONLY a JSON object:
{{"citation_support": <1-5>, "balanced_reasoning": <1-5>, "risk_disclosure": <1-5>, "overall": <weighted_avg>, "rationale": "<brief explanation>"}}
"""


@cache
def _get_judge_llm() -> ChatOpenAI:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY required for eval judge")
    return ChatOpenAI(
        model="openai/gpt-oss-20b",
        temperature=0,
        max_tokens=512,
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


async def score_analysis(analysis: dict[str, Any]) -> JudgeScore:
    """Score a single analysis output using LLM-as-judge."""
    llm = _get_judge_llm()
    prompt = JUDGE_PROMPT.format(analysis=json.dumps(analysis, indent=2))

    response = await llm.ainvoke(prompt)
    result = json.loads(response.content)

    # Calculate weighted average if not provided
    if "overall" not in result or result["overall"] == 0:
        result["overall"] = round(
            (result["citation_support"] * 0.4 +
             result["balanced_reasoning"] * 0.3 +
             result["risk_disclosure"] * 0.3), 1
        )

    return JudgeScore(**result)


async def run_eval_suite(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """Run judge on a batch of analyses. Returns aggregate metrics."""
    scores: list[JudgeScore] = []

    for analysis in analyses:
        try:
            score = await score_analysis(analysis)
            scores.append(score)
        except Exception:
            continue

    if not scores:
        return {"error": "No analyses could be scored", "count": 0}

    return {
        "count": len(scores),
        "avg_citation_support": round(sum(s.citation_support for s in scores) / len(scores), 2),
        "avg_balanced_reasoning": round(sum(s.balanced_reasoning for s in scores) / len(scores), 2),
        "avg_risk_disclosure": round(sum(s.risk_disclosure for s in scores) / len(scores), 2),
        "avg_overall": round(sum(s.overall for s in scores) / len(scores), 2),
        "scores": [s.model_dump() for s in scores],
    }
