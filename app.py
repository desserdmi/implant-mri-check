import streamlit as st
import openai
import os
from serpapi import GoogleSearch

# ⛳ Lade API-Keys aus Umgebungsvariablen
openai.api_key = os.getenv("OPENAI_API_KEY")
serpapi_key = os.getenv("SERPAPI_API_KEY")

# 🔎 Funktion: Google-Suche nach Implantaten
def search_web(query):
    params = {
        "engine": "google",
        "q": query,
        "api_key": serpapi_key,
        "num": 5,
        "hl": "de"
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    urls = [r["link"] for r in results.get("organic_results", []) if "link" in r]
    return urls

# 🧠 Funktion: GPT-Analyse mit Weblinks
def analyze_with_gpt(agg, agg_sn, sonde, sonde_sn, links):
    prompt = f"""
Du bist ein medizinischer Assistent für bildgebende Diagnostik. Analysiere die MR-Kompatibilität der folgenden Implantate:

- Aggregat: Hersteller = {agg}, Seriennummer = {agg_sn}
- Sonde: Hersteller = {sonde}, Seriennummer = {sonde_sn}

Hier sind Links zu relevanten Hersteller- oder Informationsseiten:
{chr(10).join(links)}

Liefere bitte:
- MR-Status (MR-sicher, MR-conditional, nicht MR-sicher)
- Vorbereitung vor MRT
- Zulässige Magnetfeldstärke
- SAR-Werte (Ganzkörper, Kopf)
- B1+rms
- Maximaler Gradient
- Nicht untersuchbare Körperregionen
- Nachsorge nach MRT

Antwort bitte strukturiert und in Deutsch.
"""

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

# 🖼️ Streamlit UI
st.set_page_config(page_title="MR-Kompatibilität von Implantaten", layout="centered")
st.title("🔍 MR-Kompatibilität medizinischer Implantate")

st.markdown("Gib die Daten zu Aggregat und Sonde ein, um Informationen zur MR-Gängigkeit zu erhalten.")

agg = st.text_input("Hersteller Aggregat")
agg_sn = st.text_input("Seriennummer Aggregat")

sonde = st.text_input("Hersteller Sonde")
sonde_sn = st.text_input("Seriennummer Sonde")

if st.button("Analyse starten"):
    with st.spinner("Suche nach Informationen im Web…"):
        search_query = f"{agg} {agg_sn} {sonde} {sonde_sn} MR Conditional site:medtronic.com OR site:biotronik.com OR site:bostonscientific.com"
        links = search_web(search_query)

    if not links:
        st.warning("Keine passenden Links gefunden.")
    else:
        with st.spinner("Analysiere mit GPT…"):
            result = analyze_with_gpt(agg, agg_sn, sonde, sonde_sn, links)
            st.success("Analyse abgeschlossen:")
            st.markdown(result)
