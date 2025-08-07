import streamlit as st
import os
from openai import OpenAI
from serpapi import GoogleSearch

# ---- API Keys ----
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# ---- Hersteller-Webseiten für gezielte Suche ----
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

# ---- Websuche ----
def search_web(implant_text: str, num_results: int = 10, restrict_to_manufacturers: bool = True):
    """Sucht gezielt (oder breit) nach MRI-/MR-Conditional-Infos."""
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
    results = GoogleSearch(params).get_dict()
    urls = [r.get("link") for r in results.get("organic_results", []) if r.get("link")]
    # PDFs bevorzugt vorne
    pdfs = [u for u in urls if u.lower().endswith(".pdf")]
    others = [u for u in urls if not u.lower().endswith(".pdf")]
    return (pdfs + others)[:num_results]

# ---- GPT-Auswertung ----
def analyze_with_gpt(implant_text: str, serial: str, links: list[str]) -> str:
    links_block = "\n".join(links) if links else "Keine Links gefunden."
    prompt = f"""
Du bist ein medizinischer Assistent für bildgebende Diagnostik.
Analysiere die MR-Kompatibilität des folgenden Implantats (Hersteller + Modell, ggf. Typ/Lead):

Implantat: {implant_text}
Seriennummer (falls relevant/auffindbar): {serial or "nicht angegeben"}

Nutze NUR validierte Informationen. Hier sind potenziell relevante Quellen:
{links_block}

Liefere eine strukturierte, präzise Antwort in Deutsch (leere Felder mit "k.A." kennzeichnen):

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
        model="gpt-4o",  # alternativ: "gpt-4o-mini" für günstiger & schneller
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return resp.choices[0].message.content

# ---- Streamlit UI ----
st.set_page_config(page_title="MR-Kompatibilität medizinischer Implantate", layout="centered")
st.title("🔍 MR-Kompatibilität medizinischer Implantate")
st.markdown("Gib **Hersteller + Modell** ein (z. B. „Medtronic Attesta DR ATDR01“ oder „Medtronic CapSureFix MRI SureScan“).")

implant_text = st.text_input("Implantat (Hersteller + Modell)", placeholder="z. B. Medtronic Attesta DR ATDR01")
serial = st.text_input("Seriennummer (optional)")

if st.button("Suche starten", disabled=not implant_text.strip()):
    with st.spinner("🔎 Suche auf Hersteller-Webseiten..."):
        links = search_web(implant_text)

    # Falls keine Treffer → breitere Suche im gesamten Web
    if not links:
        st.warning("⚠️ Keine direkten Treffer auf Herstellerseiten gefunden – starte erweiterte Suche im gesamten Web...")
        with st.spinner("🌐 Führe erweiterte Suche durch..."):
            links = search_web(implant_text, restrict_to_manufacturers=False)

    if not links:
        st.error("❌ Leider keine passenden Informationen gefunden. Bitte andere Schreibweise oder Modellbezeichnung versuchen.")
    else:
        with st.spinner("🧠 Analysiere Informationen..."):
            result = analyze_with_gpt(implant_text, serial, links)
        st.success("✅ Analyse abgeschlossen")
        st.markdown(result)
