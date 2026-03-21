"""Gemini-powered analyst brief: system prompt + JSON output + deterministic metrics."""

from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any

import google.generativeai as genai
import streamlit as st

_DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = """You are the credit analyst engine for FinServe (demo).
Your job is to read the structured facts and metrics supplied by the application (they are authoritative).
Do NOT invent bank balances or transactions.

You MUST reply with a single JSON object only — no markdown, no code fences, no text before or after the JSON.

JSON schema (all keys required):
{
  "verdict": "Approve" | "Conditional" | "Reject",
  "safety_score": <integer 0-100, higher = safer/more acceptable exposure for this demo>,
  "rationale": "<2-4 short sentences, plain English>",
  "risks": ["<risk1>", "<risk2>"],
  "conditions": "<empty string if verdict is Approve or Reject; otherwise brief conditions>"
}

Rules:
- safety_score must align with the supplied leverage metrics (higher leverage → lower score).
- risks: exactly 2 items, each under 120 characters.
- rationale must reference at least one numeric metric (ratio or percentage) from the input.
- Base your assessment only on the application metrics provided."""


def _resolve_model_name() -> str:
    try:
        override = str(st.secrets.get("GEMINI_MODEL", "") or "").strip()
    except Exception:
        override = ""
    if override:
        return override
    return (os.getenv("GEMINI_MODEL") or "").strip() or _DEFAULT_MODEL


def compute_financial_metrics(
    *,
    loan_amount_usd: float,
    annual_revenue_usd: float,
    existing_debt_usd: float,
) -> dict[str, Any]:
    """Deterministic ratios for the UI; avoids empty or hallucinated numbers."""
    loan = max(0.0, float(loan_amount_usd))
    rev = max(0.0, float(annual_revenue_usd))
    debt = max(0.0, float(existing_debt_usd))
    post_debt = debt + loan

    if rev <= 0:
        return {
            "annual_revenue_usd": rev,
            "existing_debt_usd": debt,
            "loan_requested_usd": loan,
            "post_loan_total_debt_usd": post_debt,
            "debt_to_revenue_pct": None,
            "loan_to_revenue_pct": None,
            "combined_leverage_pct": None,
            "revenue_note": "Annual revenue is zero or missing — ratios cannot be computed.",
        }

    return {
        "annual_revenue_usd": rev,
        "existing_debt_usd": debt,
        "loan_requested_usd": loan,
        "post_loan_total_debt_usd": post_debt,
        "debt_to_revenue_pct": round(100.0 * debt / rev, 2),
        "loan_to_revenue_pct": round(100.0 * loan / rev, 2),
        "combined_leverage_pct": round(100.0 * post_debt / rev, 2),
        "revenue_note": None,
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw)
    if not raw.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            raw = m.group(0)
    return json.loads(raw)


def _fallback_brief(metrics: dict[str, Any]) -> dict[str, Any]:
    cl = metrics.get("combined_leverage_pct")
    if cl is None:
        score = 35
        verdict = "Conditional"
        rationale = "Revenue is missing or zero; leverage ratios cannot be computed. Further financial disclosure is required before approval."
    elif cl > 80:
        score = max(15, min(45, int(100 - cl)))
        verdict = "Reject"
        rationale = f"Combined debt after this loan would be {cl:.1f}% of annual revenue — leverage is too high for a standard approval in this demo."
    elif cl > 55:
        score = max(40, min(72, int(100 - cl * 0.65)))
        verdict = "Conditional"
        rationale = f"Combined leverage near {cl:.1f}% of revenue warrants tighter structure or additional collateral."
    else:
        score = max(55, min(92, int(100 - cl * 0.5)))
        verdict = "Approve"
        rationale = f"Leverage after funding stays near {cl:.1f}% of revenue — within a workable band for this screening."

    return {
        "verdict": verdict,
        "safety_score": score,
        "rationale": rationale,
        "risks": [
            "Industry and macro volatility not fully captured in this demo.",
            "Information is self-reported and not independently verified here.",
        ],
        "conditions": "Standard covenants and periodic reporting (demo)." if verdict == "Conditional" else "",
    }


def _build_user_prompt(
    *,
    memo_date: str,
    company_name: str,
    industry: str,
    loan_purpose: str,
    metrics: dict[str, Any],
) -> str:
    m_json = json.dumps(metrics, indent=2)
    return f"""Date: {memo_date}

Applicant:
- Company: {company_name}
- Industry: {industry}
- Loan purpose: {loan_purpose or "Not specified"}

Authoritative metrics (use these numbers in your rationale):

metrics_json:
{m_json}

Produce the JSON response as specified in your system instructions."""


def generate_analyst_brief(
    *,
    company_name: str,
    industry: str,
    loan_amount_usd: float,
    loan_purpose: str,
    annual_revenue_usd: float,
    existing_debt_usd: float,
) -> dict[str, Any]:
    """Returns metrics + model JSON fields; safe for Streamlit display."""
    try:
        api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "GEMINI_API_KEY is missing. Add it to .streamlit/secrets.toml (Streamlit secrets)."
        ) from exc
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is missing. Add it to .streamlit/secrets.toml (Streamlit secrets)."
        )

    genai.configure(api_key=api_key)

    memo_date = date.today().strftime("%B %d, %Y")
    metrics = compute_financial_metrics(
        loan_amount_usd=loan_amount_usd,
        annual_revenue_usd=annual_revenue_usd,
        existing_debt_usd=existing_debt_usd,
    )

    user_prompt = _build_user_prompt(
        memo_date=memo_date,
        company_name=company_name.strip(),
        industry=industry,
        loan_purpose=loan_purpose.strip(),
        metrics=metrics,
    )

    model = genai.GenerativeModel(
        _resolve_model_name(),
        system_instruction=SYSTEM_INSTRUCTION,
    )

    generation_config = genai.GenerationConfig(
        temperature=0.35,
        max_output_tokens=1024,
    )

    response = model.generate_content(
        user_prompt,
        generation_config=generation_config,
    )

    text = (response.text or "").strip()
    ai: dict[str, Any]
    if not text:
        ai = _fallback_brief(metrics)
    else:
        try:
            parsed = _extract_json_object(text)
            ai = {
                "verdict": str(parsed.get("verdict", "Conditional")),
                "safety_score": int(parsed.get("safety_score", 50)),
                "rationale": str(parsed.get("rationale", "")).strip(),
                "risks": list(parsed.get("risks", []))[:3],
                "conditions": str(parsed.get("conditions", "")).strip(),
            }
            ai["safety_score"] = max(0, min(100, ai["safety_score"]))
            if len(ai["risks"]) < 2:
                ai["risks"] = (ai["risks"] + ["Residual model risk in demo mode."])[:2]
        except (json.JSONDecodeError, TypeError, ValueError):
            ai = _fallback_brief(metrics)

    return {
        "metrics": metrics,
        "verdict": ai["verdict"],
        "safety_score": ai["safety_score"],
        "rationale": ai["rationale"],
        "risks": ai["risks"][:3],
        "conditions": ai.get("conditions", ""),
    }
