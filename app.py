import os
import re
import pandas as pd
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
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return resp.choices[0].message.content

# ---------- Ausgabe-Bereinigung ----------
def clean_output(text: str) -> str:
    filtered_lines = [ln for ln in text.split("\n") if "k.A." not in ln.strip()]
    no_parentheses = [re.sub(r"\([^)]*\)", "", ln).strip() for ln in filtered_lines]
    return "\n".join([ln for ln in no_parentheses if ln]).strip()

# ---------- Streamlit UI ----------
st.set_page_config(page_title="MR-Kompatibilität medizinischer Implantate", layout="centered")
st.title("🔍 MR-Kompatibilität medizinischer Implantate")

mode = st.radio("Wähle den Modus:", ["Einzelabfrage", "Liste hochladen"])

if mode == "Einzelabfrage":
    col1, col2 = st.columns(2)
    with col1:
        hersteller = st.text_input("Hersteller", placeholder="z. B. Medtronic").strip()
    with col2:
        modell = st.text_input("Modell", placeholder="z. B. Attesta DR ATDR01").strip()

    if st.button("Suche starten", disabled=not hersteller or not modell):
        with st.spinner("🔎 Suche gestartet"):
            links = search_web(hersteller, modell)
        if not links:
            st.warning("⚠️ Starte erweiterte Suche…")
            with st.spinner("🌐 Führe erweiterte Suche durch..."):
                links = search_web(hersteller, modell, restrict_to_manufacturers=False)
        if not links:
            st.error("❌ Keine passenden Informationen gefunden.")
        else:
            with st.spinner("🧠 Analysiere Informationen..."):
                result = analyze_with_gpt(hersteller, modell, links)
            st.success("✅ Analyse abgeschlossen")
            st.markdown(clean_output(result))

elif mode == "Liste hochladen":
    uploaded_file = st.file_uploader("CSV oder Excel mit Spalten: Hersteller, Modell", type=["csv", "xlsx"])
    if uploaded_file is not None:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        if not {"Hersteller", "Modell"}.issubset(df.columns):
            st.error("❌ Die Datei muss die Spalten 'Hersteller' und 'Modell' enthalten.")
        else:
            results_list = []
            for idx, row in df.iterrows():
                hersteller = str(row["Hersteller"]).strip()
                modell = str(row["Modell"]).strip()
                if not hersteller or not modell:
                    continue

                with st.spinner(f"Analysiere {hersteller} {modell}..."):
                    links = search_web(hersteller, modell)
                    if not links:
                        links = search_web(hersteller, modell, restrict_to_manufacturers=False)
                    if not links:
                        result_text = "Keine passenden Informationen gefunden."
                    else:
                        result_text = clean_output(analyze_with_gpt(hersteller, modell, links))

                results_list.append({
                    "Hersteller": hersteller,
                    "Modell": modell,
                    "Ergebnis": result_text
                })

            # In DataFrame umwandeln
            results_df = pd.DataFrame(results_list)

            # Excel-Datei erzeugen
            output_path = "mr_kompatibilitaet_ergebnisse.xlsx"
            results_df.to_excel(output_path, index=False)

            # Download-Link
            with open(output_path, "rb") as f:
                st.download_button(
                    label="📥 Ergebnisse als Excel herunterladen",
                    data=f,
                    file_name=output_path,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
