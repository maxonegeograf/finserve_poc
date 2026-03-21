"""FinServe POC — Streamlit loan application, analyst view, and CRM POC."""

from __future__ import annotations

import html
import uuid
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from mailer import send_html_email
from memo_generator import generate_analyst_brief

st.set_page_config(
    page_title="FinServe POC",
    layout="wide",
    initial_sidebar_state="collapsed",
)

INDUSTRIES: tuple[str, ...] = (
    "Manufacturing",
    "Retail",
    "Wholesale & distribution",
    "Technology & software",
    "Financial services",
    "Healthcare & life sciences",
    "Professional services",
    "Construction & real estate",
    "Transportation & logistics",
    "Energy & utilities",
    "Agriculture & food",
    "Hospitality & leisure",
    "Education",
    "Media & communications",
    "Aerospace & defense",
    "Automotive",
    "Consumer goods",
    "Pharmaceuticals",
    "Other",
)

st.markdown(
    """
    <style>
    .finserve-title { font-size: 1.75rem; font-weight: 650; margin-bottom: 0.25rem; }
    .finserve-sub { color: #5f6368; font-size: 0.95rem; margin-bottom: 1.25rem; }
    .decision-banner { padding: 14px 18px; border-radius: 10px; font-weight: 600; font-size: 1.05rem; margin: 10px 0 14px 0; }
    .decision-reject { background: #fdecea; color: #b3261e; border: 1px solid #f5c6c0; }
    .decision-approve { background: #e8f5e9; color: #1b5e20; border: 1px solid #a5d6a7; }
    .decision-conditional { background: #fff8e1; color: #e65100; border: 1px solid #ffcc80; }
    .crm-big-btn button { font-size: 1.1rem !important; padding: 0.65rem 1.25rem !important; }
    @keyframes finserve-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.65; transform: scale(0.995); }
    }
    .finserve-loading-text {
      animation: finserve-pulse 1.35s ease-in-out infinite;
      font-weight: 600;
      color: #1a73e8;
      margin: 0.75rem 0 0.25rem 0;
      font-size: 1.02rem;
    }
    .finserve-loading-sub { color: #5f6368; font-size: 0.9rem; margin-bottom: 0.75rem; }
    .form-section-title {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #5f6368;
      margin: 0 0 0.65rem 0;
    }
    .finserve-doc {
      border: 1px solid #dadce0; border-radius: 12px; padding: 1.35rem 1.6rem;
      background: linear-gradient(180deg, #fafafa 0%, #ffffff 50%);
      box-shadow: 0 1px 3px rgba(60,64,67,.1);
      margin-top: 1rem;
      color: #202124 !important;
    }
    .finserve-doc h2 { margin: 0 0 0.35rem 0; font-size: 1.35rem; letter-spacing: -0.02em; }
    .finserve-doc .meta { color: #5f6368 !important; font-size: 0.88rem; margin-bottom: 1.1rem; }
    .finserve-doc .body { font-size: 0.96rem; line-height: 1.6; color: #202124 !important; }
    .finserve-doc .highlight-box {
      background: #f8f9fa;
      border-left: 4px solid #1a73e8;
      padding: 0.85rem 1rem;
      margin: 1rem 0;
      border-radius: 0 8px 8px 0;
      color: #202124 !important;
    }
    .finserve-doc .highlight-box p { color: #202124 !important; margin: 0; }
    .finserve-doc .cta-box {
      background: #e8f0fe;
      border: 1px solid #aecbfa;
      border-radius: 10px;
      padding: 1rem 1.15rem;
      margin-top: 1.25rem;
      text-align: center;
    }
    .finserve-doc .cta-box p { color: #202124 !important; }
    .finserve-doc .cta-box p.cta-title { color: #174ea6 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

for key, default in (
    ("client_data", None),
    ("analyst_brief", None),
    ("decision_msg", None),
    ("crm_records", []),
    ("last_submission_id", None),
    ("view", "workspace"),
    ("crm_editor_bump", 0),
    ("client_outcome_html", None),
    ("client_outcome_kind", None),
    ("notice_screening_email", None),
    ("notice_decision_email", None),
    ("client_accept_notice", None),
):
    if key not in st.session_state:
        st.session_state[key] = default


def _format_usd(n: float) -> str:
    return f"${n:,.0f}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}%"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _indicative_apr(safety_score: int) -> float:
    """Demo indicative APR derived from safety score (not a real pricing engine)."""
    s = max(0, min(100, int(safety_score)))
    return round(5.25 + (100 - s) * 0.085, 2)


def _decision_banner_class(verdict: str) -> str:
    v = (verdict or "").strip().lower()
    if v == "reject":
        return "decision-reject"
    if v == "approve":
        return "decision-approve"
    return "decision-conditional"


def _render_ai_decision(verdict: str) -> None:
    safe = html.escape(verdict.strip())
    cls = _decision_banner_class(verdict)
    st.markdown(
        f'<div class="decision-banner {cls}">AI decision: {safe}</div>',
        unsafe_allow_html=True,
    )


def _crm_status_options() -> list[str]:
    return [
        "New",
        "Under review",
        "Conditional",
        "Offer sent",
        "Client accepted",
        "Rejected",
        "Withdrawn",
    ]


def _map_ai_to_status(ai_verdict: str) -> str:
    m = (ai_verdict or "").strip()
    if m == "Conditional":
        return "Conditional"
    return "Under review"


def _add_crm_record(*, client_data: dict, brief: dict | None) -> str:
    rid = str(uuid.uuid4())
    ai_v = (brief or {}).get("verdict", "—")
    score = (brief or {}).get("safety_score", "—")
    rationale = ((brief or {}).get("rationale") or "")[:280]
    rec = {
        "id": rid,
        "company": client_data["company_name"],
        "industry": client_data["industry"],
        "loan_usd": client_data["loan_amount_usd"],
        "status": _map_ai_to_status(str(ai_v)),
        "notes": "",
        "ai_verdict": str(ai_v),
        "safety_score": score if isinstance(score, int) else score,
        "rationale_excerpt": rationale,
        "client_message": "",
        "updated_at": _now_iso(),
    }
    st.session_state.crm_records = [rec] + list(st.session_state.crm_records)
    st.session_state.crm_editor_bump = int(st.session_state.crm_editor_bump) + 1
    return rid


def _update_crm_record(rid: str, **fields: object) -> None:
    out = []
    for r in st.session_state.crm_records:
        if r["id"] == rid:
            nr = {**r, **fields, "updated_at": _now_iso()}
            out.append(nr)
        else:
            out.append(r)
    st.session_state.crm_records = out


def _find_record(rid: str) -> dict | None:
    for r in st.session_state.crm_records:
        if r["id"] == rid:
            return r
    return None


def _html_screening_result(company: str, brief: dict) -> str:
    co = html.escape(company)
    v = html.escape(str(brief.get("verdict", "—")))
    score = brief.get("safety_score", "—")
    rat = html.escape(str(brief.get("rationale", "")))
    risks = brief.get("risks") or []
    risks_html = "".join(f"<li>{html.escape(str(x))}</li>" for x in risks[:3])
    return f"""
<div class="finserve-doc" style="font-family: system-ui, Segoe UI, sans-serif; color: #202124;">
  <h2 style="color:#1967d2;">FinServe — preliminary screening result</h2>
  <div class="meta">{html.escape(_now_iso())} · {co}</div>
  <p><b>Screening outcome:</b> {v} · <b>Safety score:</b> {html.escape(str(score))} / 100</p>
  <p class="body">{rat}</p>
  <p><b>Key risks:</b></p>
  <ul>{risks_html}</ul>
  <p style="font-size:0.85rem;color:#5f6368;">This is an automated demo assessment. A relationship manager will make the final credit decision.</p>
</div>
"""


def _html_approval_offer(
    *,
    company: str,
    loan_usd: float,
    analyst_note: str,
    safety_score: int,
    term_months_min: int,
    term_months_max: int,
) -> str:
    co = html.escape(company)
    amt = html.escape(_format_usd(loan_usd))
    apr = _indicative_apr(safety_score)
    note = analyst_note.strip()
    note_html = html.escape(note) if note else "No additional comments."
    tmin = int(term_months_min)
    tmax = int(term_months_max)
    return f"""
<div class="finserve-doc" style="font-family: system-ui, Segoe UI, sans-serif; color: #202124;">
  <h2 style="color:#137333;">Congratulations — your financing request is approved in principle</h2>
  <div class="meta">{html.escape(_now_iso())} · {co}</div>
  <p class="body">
    We are pleased to inform you that, following analyst review, <b>FinServe approves your requested facility
    of {amt}</b> subject to documentation, verification, and final credit committee sign-off (demo workflow).
  </p>
  <div class="highlight-box">
    <p style="margin:0 0 0.5rem 0;color:#202124;"><b>Indicative terms (demo)</b></p>
    <p style="margin:0;color:#202124;">
      <b>Indicative APR:</b> {apr:.2f}% per annum (fixed for illustration)<br/>
      <b>Amortization window:</b> {tmin} to {tmax} months (select within this range at closing)<br/>
      <b>Underwriting score:</b> {int(safety_score)} / 100 (internal)
    </p>
  </div>
  <p class="body">
    These figures are <b>indicative only</b> and may change after full diligence. Your analyst’s note:
  </p>
  <p class="body" style="background:#fff;border:1px solid #e8eaed;border-radius:8px;padding:0.75rem 1rem;">{note_html}</p>
  <div class="cta-box">
    <p class="cta-title" style="margin:0 0 0.5rem 0;font-weight:600;color:#174ea6;">Next step</p>
    <p style="margin:0;font-size:0.95rem;color:#202124;">
      If you wish to proceed under these indicative terms, please return to the application portal and click
      <b>“I accept this offer and wish to proceed”</b> below. We will then move your file to onboarding.
    </p>
  </div>
  </div>
"""


def _html_rejection_letter(*, company: str, loan_usd: float, analyst_note: str, brief: dict | None) -> str:
    co = html.escape(company)
    amt = html.escape(_format_usd(loan_usd))
    note = analyst_note.strip()
    note_html = html.escape(note) if note else "—"
    rationale = html.escape(str((brief or {}).get("rationale", "") or ""))[:600]
    return f"""
<div class="finserve-doc" style="font-family: system-ui, Segoe UI, sans-serif; color: #202124;">
  <h2 style="color:#b3261e;">Update on your financing application</h2>
  <div class="meta">{html.escape(_now_iso())} · {co}</div>
  <p class="body">
    Thank you for choosing FinServe and for the time you invested in your application. After careful review,
    we <b>regret that we are unable to approve</b> the requested facility of <b>{amt}</b> at this time.
  </p>
  <p class="body">
    This decision reflects our current risk appetite and the information available in this demo assessment.
    It is <b>not</b> a reflection of your organization’s worth, and we would welcome a future conversation
    should your financial profile evolve.
  </p>
  <p><b>Analyst summary for your records:</b></p>
  <p class="body" style="background:#fafafa;border:1px solid #e8eaed;border-radius:8px;padding:0.75rem 1rem;">{rationale}</p>
  <p><b>Relationship manager note:</b></p>
  <p class="body" style="background:#fff;border:1px solid #fce8e6;border-radius:8px;padding:0.75rem 1rem;">{note_html}</p>
  <p style="font-size:0.85rem;color:#5f6368;">If you have questions, please reply to your FinServe contact. FinServe POC — demo only.</p>
</div>
"""


def render_workspace() -> None:
    left, right = st.columns(2, gap="large")

    with left:
        st.subheader("Client application")

        with st.container(border=True):
            st.caption(
                "Complete all sections. Your request is scored automatically; a manager then reviews the file."
            )
            st.markdown('<p class="form-section-title">Company</p>', unsafe_allow_html=True)
            with st.form("loan_application", clear_on_submit=False):
                c1, c2 = st.columns(2)
                with c1:
                    company_name = st.text_input("Legal company name", placeholder="Acme Manufacturing LLC")
                with c2:
                    industry = st.selectbox("Industry", INDUSTRIES, index=0)

                st.markdown('<p class="form-section-title">Loan request</p>', unsafe_allow_html=True)
                loan_amount = st.number_input(
                    "Requested loan amount (USD)",
                    min_value=0.0,
                    value=100_000.0,
                    step=1_000.0,
                    format="%.2f",
                )
                loan_purpose = st.text_area(
                    "Purpose of funds",
                    placeholder="Working capital, equipment purchase, expansion, refinancing…",
                    height=88,
                )
                tc1, tc2 = st.columns(2)
                with tc1:
                    term_months_min = st.number_input(
                        "Preferred term — minimum (months)",
                        min_value=6,
                        max_value=120,
                        value=24,
                        step=6,
                    )
                with tc2:
                    term_months_max = st.number_input(
                        "Preferred term — maximum (months)",
                        min_value=6,
                        max_value=120,
                        value=60,
                        step=6,
                    )

                st.markdown('<p class="form-section-title">Financials (self-reported)</p>', unsafe_allow_html=True)
                f1, f2 = st.columns(2)
                with f1:
                    annual_revenue = st.number_input(
                        "Annual revenue (USD)",
                        min_value=0.0,
                        value=500_000.0,
                        step=25_000.0,
                        format="%.2f",
                    )
                with f2:
                    existing_debt = st.number_input(
                        "Existing debt (USD)",
                        min_value=0.0,
                        value=0.0,
                        step=10_000.0,
                        format="%.2f",
                    )

                st.markdown('<p class="form-section-title">Notifications</p>', unsafe_allow_html=True)
                client_email = st.text_input(
                    "Email for notifications (optional)",
                    placeholder="client@company.com",
                    help="Screening results and final letters can be emailed when SMTP is configured in .env.",
                )
                submitted = st.form_submit_button("Submit application", type="primary", use_container_width=True)

        if submitted:
            st.session_state.decision_msg = None
            st.session_state.notice_screening_email = None
            st.session_state.notice_decision_email = None
            st.session_state.client_outcome_html = None
            st.session_state.client_outcome_kind = None
            st.session_state.client_accept_notice = None

            if not (company_name or "").strip():
                st.error("Please enter the company name.")
            else:
                tmin = int(term_months_min)
                tmax = int(term_months_max)
                if tmin > tmax:
                    tmin, tmax = tmax, tmin

                st.session_state.client_data = {
                    "company_name": company_name.strip(),
                    "industry": industry,
                    "loan_amount_usd": float(loan_amount),
                    "loan_purpose": (loan_purpose or "").strip(),
                    "annual_revenue_usd": float(annual_revenue),
                    "existing_debt_usd": float(existing_debt),
                    "client_email": (client_email or "").strip(),
                    "term_months_min": tmin,
                    "term_months_max": tmax,
                }

                st.markdown("---")
                st.markdown(
                    '<p class="finserve-loading-text">Our analysts are reviewing your application — please wait…</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<p class="finserve-loading-sub">Risk scoring and AI recommendation are generated automatically.</p>',
                    unsafe_allow_html=True,
                )

                try:
                    with st.spinner(" "):
                        st.session_state.analyst_brief = generate_analyst_brief(
                            company_name=st.session_state.client_data["company_name"],
                            industry=st.session_state.client_data["industry"],
                            loan_amount_usd=st.session_state.client_data["loan_amount_usd"],
                            loan_purpose=st.session_state.client_data["loan_purpose"],
                            annual_revenue_usd=st.session_state.client_data["annual_revenue_usd"],
                            existing_debt_usd=st.session_state.client_data["existing_debt_usd"],
                        )
                        st.session_state.last_submission_id = _add_crm_record(
                            client_data=st.session_state.client_data,
                            brief=st.session_state.analyst_brief,
                        )

                    em = st.session_state.client_data.get("client_email") or ""
                    if em and st.session_state.analyst_brief:
                        subj = "FinServe — preliminary screening result"
                        body = _html_screening_result(
                            st.session_state.client_data["company_name"],
                            st.session_state.analyst_brief,
                        )
                        ok, msg = send_html_email(
                            to_addr=em,
                            subject=subj,
                            html_body=body,
                            text_fallback="Your preliminary screening result is ready (demo).",
                        )
                        st.session_state.notice_screening_email = ("ok" if ok else "warn", msg)

                except Exception as exc:
                    st.session_state.analyst_brief = None
                    st.error(f"Screening failed: {exc}")

        if st.session_state.get("notice_screening_email"):
            kind, msg = st.session_state.notice_screening_email
            if kind == "ok":
                st.success(msg)
            else:
                st.info(msg)

        if st.session_state.get("client_outcome_html"):
            st.markdown("---")
            st.markdown("#### Your outcome letter")
            st.markdown(st.session_state.client_outcome_html, unsafe_allow_html=True)

            sid = st.session_state.last_submission_id
            rec = _find_record(sid) if sid else None
            if (
                st.session_state.get("client_outcome_kind") == "approve"
                and rec
                and rec.get("status") == "Offer sent"
            ):
                st.markdown("")
                if st.button("I accept this offer and wish to proceed", type="primary", key="client_accept_offer"):
                    _update_crm_record(sid, status="Client accepted")
                    st.session_state.client_accept_notice = (
                        "Thank you — your acceptance has been recorded. Our team will contact you for onboarding (demo)."
                    )
                    st.rerun()

        if st.session_state.get("client_accept_notice"):
            st.success(st.session_state.client_accept_notice)

        if st.session_state.get("notice_decision_email"):
            kind, msg = st.session_state.notice_decision_email
            if kind == "ok":
                st.success(msg)
            else:
                st.info(msg)

    with right:
        st.subheader("CRM / Analyst")

        if st.session_state.client_data is None:
            st.info(
                "Submit an application on the left. Metrics, **AI decision**, and **Approve** / **Decline** "
                "actions will appear here. Approvals publish an offer to the client and set CRM to **Offer sent**."
            )
        else:
            d = st.session_state.client_data
            brief = st.session_state.analyst_brief

            with st.container(border=True):
                st.caption("Applicant")
                st.markdown(f"**{d['company_name']}** · {d['industry']}")
                if d.get("loan_purpose"):
                    st.caption(d["loan_purpose"])
                st.caption(
                    f"Loan {_format_usd(d['loan_amount_usd'])} · "
                    f"Revenue {_format_usd(d['annual_revenue_usd'])} · "
                    f"Debt {_format_usd(d['existing_debt_usd'])} · "
                    f"Term {d.get('term_months_min', '—')}–{d.get('term_months_max', '—')} mo."
                )
                if d.get("client_email"):
                    st.caption(f"Email: {d['client_email']}")

                st.divider()

                if not brief:
                    st.warning("Recommendation unavailable — see the error on the left.")
                else:
                    m = brief["metrics"]
                    r1, r2, r3 = st.columns(3)
                    with r1:
                        st.metric("Debt / revenue", _fmt_pct(m.get("debt_to_revenue_pct")))
                    with r2:
                        st.metric("Loan / revenue", _fmt_pct(m.get("loan_to_revenue_pct")))
                    with r3:
                        st.metric("Total debt after loan / revenue", _fmt_pct(m.get("combined_leverage_pct")))

                    if m.get("revenue_note"):
                        st.caption(m["revenue_note"])

                    st.divider()

                    sc1, sc2 = st.columns([1, 2])
                    with sc1:
                        st.metric(
                            "Client safety score",
                            f"{brief['safety_score']} / 100",
                            help="Demo risk score based on self-reported figures.",
                        )
                    with sc2:
                        verdict = brief["verdict"]
                        _render_ai_decision(verdict)

                    st.markdown(brief["rationale"])

                    st.markdown("**Key risks**")
                    for risk in brief.get("risks", []):
                        st.markdown(f"- {risk}")

                    cond = (brief.get("conditions") or "").strip()
                    if cond and verdict == "Conditional":
                        st.info(f"**Conditions:** {cond}")

                    st.divider()
                    analyst_note = st.text_input(
                        "Analyst note (shown to the client in the letter)",
                        key="analyst_note_input",
                        placeholder="Short rationale the client will read",
                    )

                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("Approve & send offer", type="primary", use_container_width=True, key="btn_app"):
                            st.session_state.decision_msg = "Offer published to the client (demo)."
                            sid = st.session_state.last_submission_id
                            brief_local = st.session_state.analyst_brief or {}
                            score = int(brief_local.get("safety_score", 70))
                            doc = _html_approval_offer(
                                company=d["company_name"],
                                loan_usd=d["loan_amount_usd"],
                                analyst_note=analyst_note,
                                safety_score=score,
                                term_months_min=int(d.get("term_months_min", 24)),
                                term_months_max=int(d.get("term_months_max", 60)),
                            )
                            st.session_state.client_outcome_html = doc
                            st.session_state.client_outcome_kind = "approve"
                            st.session_state.notice_decision_email = None
                            st.session_state.client_accept_notice = None
                            if sid:
                                _update_crm_record(sid, status="Offer sent")
                            em = d.get("client_email") or ""
                            if em:
                                ok, msg = send_html_email(
                                    to_addr=em,
                                    subject="FinServe — credit decision (approval in principle)",
                                    html_body=doc,
                                    text_fallback="Your application has been approved in principle (demo).",
                                )
                                st.session_state.notice_decision_email = ("ok" if ok else "warn", msg)
                            else:
                                st.session_state.notice_decision_email = (
                                    "warn",
                                    "No email on file — the letter is shown only on the left.",
                                )
                            st.rerun()
                    with b2:
                        if st.button("Decline", use_container_width=True, key="btn_rej"):
                            st.session_state.decision_msg = "Application declined (demo)."
                            sid = st.session_state.last_submission_id
                            doc = _html_rejection_letter(
                                company=d["company_name"],
                                loan_usd=d["loan_amount_usd"],
                                analyst_note=analyst_note,
                                brief=brief,
                            )
                            st.session_state.client_outcome_html = doc
                            st.session_state.client_outcome_kind = "reject"
                            st.session_state.notice_decision_email = None
                            st.session_state.client_accept_notice = None
                            if sid:
                                _update_crm_record(sid, status="Rejected")
                            em = d.get("client_email") or ""
                            if em:
                                ok, msg = send_html_email(
                                    to_addr=em,
                                    subject="FinServe — credit decision",
                                    html_body=doc,
                                    text_fallback="We are unable to approve your request at this time (demo).",
                                )
                                st.session_state.notice_decision_email = ("ok" if ok else "warn", msg)
                            else:
                                st.session_state.notice_decision_email = (
                                    "warn",
                                    "No email on file — the letter is shown only on the left.",
                                )
                            st.rerun()

                    if st.session_state.decision_msg:
                        st.success(st.session_state.decision_msg)


def render_crm_poc() -> None:
    st.subheader("CRM POC — pipeline")
    st.caption(
        "Session-only data (cleared when the app restarts). Edit **status** and **notes**, then save."
    )

    if not st.session_state.crm_records:
        st.warning("No applications yet. Submit the form on the main screen.")
        return

    rows = []
    for r in st.session_state.crm_records:
        rows.append(
            {
                "id": r["id"],
                "company": r["company"],
                "industry": r["industry"],
                "loan_usd": r["loan_usd"],
                "status": r["status"],
                "notes": r.get("notes", ""),
                "ai_verdict": r.get("ai_verdict", ""),
                "safety_score": r.get("safety_score", ""),
                "rationale_excerpt": r.get("rationale_excerpt", ""),
                "client_message": r.get("client_message", ""),
                "updated_at": r.get("updated_at", ""),
            }
        )
    df = pd.DataFrame(rows)

    editor_key = f"crm_editor_{st.session_state.crm_editor_bump}"
    edited = st.data_editor(
        df,
        column_config={
            "id": None,
            "company": st.column_config.TextColumn("Company", disabled=True, width="medium"),
            "industry": st.column_config.TextColumn("Industry", disabled=True),
            "loan_usd": st.column_config.NumberColumn("Loan (USD)", format="$%.0f", disabled=True),
            "status": st.column_config.SelectboxColumn("Status", options=_crm_status_options(), required=True),
            "notes": st.column_config.TextColumn("Notes", width="large"),
            "ai_verdict": st.column_config.TextColumn("AI verdict", disabled=True),
            "safety_score": st.column_config.TextColumn("Score", disabled=True),
            "rationale_excerpt": st.column_config.TextColumn("AI summary", disabled=True, width="large"),
            "client_message": st.column_config.TextColumn("Client letter", width="large"),
            "updated_at": st.column_config.TextColumn("Updated", disabled=True),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=editor_key,
    )

    if st.button("Save to CRM", type="primary", key="crm_save"):
        if edited is not None and not edited.empty:
            for _, row in edited.iterrows():
                _update_crm_record(
                    str(row["id"]),
                    status=str(row["status"]),
                    notes=str(row.get("notes", "")),
                    client_message=str(row.get("client_message", "")),
                )
        st.success("Saved.")
        st.rerun()


def main() -> None:
    top1, top2, _ = st.columns([2, 1, 1])
    with top1:
        st.markdown('<p class="finserve-title">FinServe POC</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="finserve-sub">Loan application · AI screening · CRM (demo)</p>',
            unsafe_allow_html=True,
        )
    with top2:
        st.markdown('<div class="crm-big-btn">', unsafe_allow_html=True)
        if st.session_state.view == "workspace":
            if st.button("Open CRM POC", type="primary", use_container_width=True, key="open_crm"):
                st.session_state.view = "crm"
                st.rerun()
        else:
            if st.button("← Back to application", use_container_width=True, key="back_ws"):
                st.session_state.view = "workspace"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.view == "crm":
        render_crm_poc()
    else:
        render_workspace()


if __name__ == "__main__":
    main()
