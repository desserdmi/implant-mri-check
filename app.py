import os
import time
import streamlit as st
from typing import List
from openai import OpenAI, APIError, RateLimitError
from serpapi import GoogleSearch

# ---------- API-Setup ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

st.set_page_config(page_title="MR-Kompatibilität medizinischer Implantate", layout="centered")

if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY fehlt in den Streamlit Secrets. Bitte in Settings → Secrets eintragen.")
if not SERPAPI_API_KEY:
    st.error("SERPAPI_API_KEY fehlt in den Streamlit Secrets. Bitte in Settings → Secrets eintragen.")

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------- Hersteller-Domains für fokussierte Suche ----------
MANUFACTURER_SITES = [
    "medtronic.com",
    "biotronik.com",
    "bostonscientific.com",
    "abbott.com",
    "sorin.com",
    "microport.com",
    "biomet.com",
    "stryker.com",
]

# ---------- Hilfsfunktionen ----------
def serpapi_search(query: str, num_results: int = 10, retries: int = 2, backoff: float = 1.5) -> List[str]:
    """SerpAPI-Wrapper mit leichtem Retry und PDF-Priorisierung."""
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": num_results,
        "hl": "de",
    }
    last_exc = None
    for attempt in range(retries + 1):
        try:
            results = GoogleSearch(params).get_dict() or {}
            org = results.get("organic_results", []) or []
            urls = [r.get("link") for r in org if r.get("link")]
            pdfs = [u for u in urls if u.lower().endswith(".pdf")]
            others = [u for u in urls if not u.lower().endswith(".pdf")]
            return (pdfs + others)[:num_results]
        except Exception as e:
            last_exc = e
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"SerpAPI-Suche fehlgeschlagen: {last_exc}")

def search_web(hersteller: str, modell: str, num_results: int = 10, restrict_to_manufacturers: bool = True) -> List[str]:
    """Sucht nach MRI-/MR-Conditional-Informationen."""
    implant_text = f"{hersteller} {modell}".strip()
    if restrict_to_manufacturers:
        sites = " OR ".join([f"site:{d}" for d in MANUFACTURER_SITES])
        query = f"\"{implant_text}\" (MRI compatibility OR MR conditional OR MRT tauglich) {sites}"
    else:
        query = f"\"{implant_text}\" (MRI compatibility OR MR conditional OR MRT tauglich)"
    return serpapi_search(query, num_results=num_results)

def analyze_with_gpt(hersteller: str, modell: str, links: List[str], model_name: str) -> str:
    links_block = "\n".join(links) if links else "Keine Links gefunden."
    prompt = f"""
Du bist ein medizinischer Assistent für bildgebende Diagnostik.
Analysiere die MR-Kompatibilität des folgenden Implantats und antworte strukturiert in Deutsch.

Hersteller: {hersteller}
Modell: {modell}

Nutze NUR validierte Informationen. Hier sind potenziell relevante Quellen:
{links_block}

Antworte im folgenden Format. Wenn eine Angabe nicht auffindbar ist, schreibe k.A.:

- MR-Status:
- Magnetfeldstärke:
- SAR-Werte:
  - Ganzkörper-SAR (W/kg):
  - Kopf-SAR (W/kg):
- B1+rms (µT):
- Max. Gradient (G/cm):
- Einschränkungen (Körperregionen/Positionierung/Scan-Modi):
- Vorbereitung (z. B. PM/ICD-Programmierung, Monitoring):
- Nachsorge:
- Quellen (URLs):

Wenn Informationen widersprüchlich oder nicht auffindbar sind, weise explizit darauf hin.
"""
    try:
        resp = client.chat.completions.create(
            model=model_name,  # "gpt-4o" oder "gpt-4o-mini"
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return resp.choices[0].message.content
    except RateLimitError as e:
        raise RuntimeError("OpenAI Rate Limit. Bitte später erneut versuchen.") from e
    except APIError as e:
        raise RuntimeError(f"OpenAI API-Fehler: {e}") from e
    except Exception as e:
        raise RuntimeError(f"OpenAI-Aufruf fehlgeschlagen: {e}") from e

# ---------- UI ----------
st.title("🔍 MR-Kompatibilität medizinischer Implantate")
st.markdown("Gib **Hersteller** und **Modell** ein (z. B. Hersteller: „Medtronic“ / Modell: „Attesta DR ATDR01“).")

with st.sidebar:
    st.header("Einstellungen")
    start_broad = st.toggle("Direkt breit suchen (nicht nur Herstellerseiten)", value=False)
    top_k = st.slider("Anzahl Links (Top-K)", 5, 20, 10)
    model_name = st.selectbox("OpenAI Modell", ["gpt-4o", "gpt-4o-mini"], index=0)
    st.caption("Tipp: *gpt-4o-mini* ist günstiger und oft ausreichend.")

col1, col2 = st.columns(2)
with col1:
    hersteller = st.text_input("Hersteller", placeholder="z. B. Medtronic").strip()
with col2:
    modell = st.text_input("Modell", placeholder="z. B. Attesta DR ATDR01").strip()

if st.button("Suche starten", disabled=not hersteller or not modell):
    if not OPENAI_API_KEY or not SERPAPI_API_KEY:
        st.stop()

    # 1) Erste Suche
    scope_msg = "Hersteller-Webseiten" if not start_broad else "gesamtes Web"
    with st.spinner(f"🔎 Suche in {scope_msg}…"):
        try:
            links = search_web(hersteller, modell, num_results=top_k, restrict_to_manufacturers=not start_broad)
        except Exception as e:
            st.error(str(e))
            st.stop()

    # 2) Falls leer und wir haben nicht bereits breit gesucht → breiter werden
    if not links and not start_broad:
        st.warning("⚠️ Keine direkten Treffer auf Herstellerseiten gefunden – starte erweiterte Suche im gesamten Web…")
        with st.spinner("🌐 Erweiterte Suche…"):
            try:
                links = search_web(hersteller, modell, num_results=top_k, restrict_to_manufacturers=False)
            except Exception as e:
                st.error(str(e))
                st.stop()

    if not links:
        st.error("❌ Leider keine passenden Informationen gefunden. Bitte Schreibweise/Modell prüfen oder ein alternatives Modell versuchen.")
        st.stop()

    # Zeige Quellen direkt an
    with st.expander("Gefundene Quellen (Top-K)"):
        for i, u in enumerate(links, 1):
            st.write(f"{i}. {u}")

    # 3) Analyse
    with st.spinner("🧠 Analysiere Informationen…"):
        try:
            result = analyze_with_gpt(hersteller, modell, links, model_name=model_name)
        except Exception as e:
            st.error(str(e))
            st.stop()

    # Optionale Reinigung: Zeilen mit 'k.A.' ausblenden
    filtered_lines = [ln for ln in result.split("\n") if "k.A." not in ln.strip()]
    clean_result = "\n".join(filtered_lines).strip()

    st.success("✅ Analyse abgeschlossen")
    st.markdown(clean_result)
