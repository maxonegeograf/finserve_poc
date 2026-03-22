# FinServe POC

A **Streamlit demo** of an AI-assisted commercial loan workflow: clients submit an application, **Google Gemini** returns a structured risk score and recommendation, analysts can **approve** (send an indicative offer) or **decline**, and a lightweight **in-session CRM** tracks statuses (e.g. *Offer sent*, *Client accepted*). Optional **SMTP** can email screening and decision letters.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Gemini API key

The app reads **`GEMINI_API_KEY`** from **[Streamlit secrets](https://docs.streamlit.io/develop/concepts/connections/secrets-management)**.

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Set your key from [Google AI Studio](https://aistudio.google.com/apikey):

```toml
GEMINI_API_KEY = "your-key-here"
```

Do **not** commit `secrets.toml`.

Optional: `GEMINI_MODEL` in the same file (defaults to `gemini-2.5-flash`).

### Email (optional)

For outbound mail, configure SMTP via environment variables or `.env` — see `.env.example` (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, etc.).

---

## Agent prompt: use a local API key instead of Streamlit secrets

Use this with your coding agent if you want Gemini to load from the environment (e.g. `.env` or shell) instead of `st.secrets`:

> In `memo_generator.py`, stop using `st.secrets["GEMINI_API_KEY"]` for the Gemini client. Load `GEMINI_API_KEY` from the process environment with `os.getenv("GEMINI_API_KEY")`, optionally after `load_dotenv()` from `python-dotenv`, and add `python-dotenv` to `requirements.txt` if missing. Keep a clear error if the key is unset. Remove or avoid importing Streamlit inside `memo_generator.py` so the module can be tested without running Streamlit. Update the README to document `.env` or exporting `GEMINI_API_KEY` for local runs.
