import os
import streamlit as st
from openai import OpenAI
from serpapi import GoogleSearch

# ---------- API-Setup ----------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

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

# ---------- Websuche ----------
def search_web(hersteller: str, modell: str, num_results: int = 10, restrict_to_manufacturers: bool = True):
    """
    Sucht nach MRI-/MR-Conditional-Informationen.
    Zuerst optional nur auf Herstellerseiten, sonst im gesamten Web.
    PDFs werden priorisiert.
    """
    implant_text = f"{hersteller} {modell}".strip()

    if restrict_to_manufacturers:
        sites = " OR ".join([f"site:{d}" for d in MANUFACTURER_SITES])
        query = f"\"{implant_text}\" (MRI compatibility OR MR conditional OR MRT tauglich) {sites}"
    else:
        query = f"\"{implant_text}\" (MRI compatibility OR MR conditional OR MRT tauglich)"

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": num_results,
        "hl": "de",
    }

    results = GoogleSearch(params).get_dict() or {}
    org = results.get("organic_results", []) or []
    urls = [r.get("link") for r in org if r.get("link")]

    # PDFs nach vorne sortieren
    pdfs = [u for u in urls if u.lower().endswith(".pdf")]
    others = [u for u in urls if not u.lower().endswith(".pdf")]
    return (pdfs + others)[:num_results]

# ---------- GPT-Analyse ----------
def analyze_with_gpt(hersteller: str, modell: str, links: list[str]) -> str:
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
    resp = client.chat.completions.create(
        model="gpt-4o",  # oder "gpt-4o-mini" für günstiger/schneller
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return resp.choices[0].message.content

# ---------- Streamlit UI ----------
st.set_page_config(page_title="MR-Kompatibilität medizinischer Implantate", layout="centered")
st.title("🔍 MR-Kompatibilität medizinischer Implantate")
st.markdown("Gib **Hersteller** und **Modell** ein (z. B. Hersteller: „Medtronic“ / Modell: „Attesta DR ATDR01“).")

col1, col2 = st.columns(2)
with col1:
    hersteller = st.text_input("Hersteller", placeholder="z. B. Medtronic").strip()
with col2:
    modell = st.text_input("Modell", placeholder="z. B. Attesta DR ATDR01").strip()

if st.button("Suche starten", disabled=not hersteller or not modell):
    with st.spinner("🔎 Suche auf Hersteller-Webseiten..."):
        links = search_web(hersteller, modell)

    # Falls keine Treffer → breitere Suche
    if not links:
        st.warning("⚠️ Keine direkten Treffer auf Herstellerseiten gefunden – starte erweiterte Suche im gesamten Web …")
        with st.spinner("🌐 Führe erweiterte Suche durch..."):
            links = search_web(hersteller, modell, restrict_to_manufacturers=False)

    if not links:
        st.error("❌ Leider keine passenden Informationen gefunden. Bitte Schreibweise/Modell prüfen oder ein alternatives Modell versuchen.")
    else:
        with st.spinner("🧠 Analysiere Informationen..."):
            result = analyze_with_gpt(hersteller, modell, links)

        # ---- Zeilen mit "k.A." entfernen ----
        filtered_lines = [ln for ln in result.split("\n") if "k.A." not in ln.strip()]
        clean_result = "\n".join(filtered_lines).strip()

        st.success("✅ Analyse abgeschlossen")
        st.markdown(clean_result)
