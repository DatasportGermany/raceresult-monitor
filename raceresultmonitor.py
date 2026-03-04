import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime

# --- KONFIGURATION ---
API_URL = "https://api.raceresult.com/386365/WOYZERNGRAW2Q7GAL2QPJPHCHE0NYCCZ"

st.set_page_config(page_title="Race Control", layout="wide")

# Hilfsfunktion zur Zeitumrechnung
def time_to_seconds(t_str):
    try:
        if not t_str or t_str == "": return 0
        h, m, s = map(float, t_str.split(':'))
        return h * 3600 + m * 60 + s
    except:
        return 0

@st.cache_data(ttl=30)
def load_data():
    res = requests.get(API_URL)
    data = res.json()
    df = pd.DataFrame(data['data'], columns=data['columns'])
    
    # Zeit-Spalten in numerische Sekunden umwandeln für Berechnungen
    # Wir nehmen an, die Spalten heißen 'Startzeit' und 'Zielzeit'
    df['Start_Sec'] = df['Startzeit'].apply(time_to_seconds)
    df['Ziel_Sec'] = df['Zielzeit'].apply(time_to_seconds)
    df['Netto_Sec'] = df['Ziel_Sec'] - df['Start_Sec']
    return df

# --- UI LOGIK ---
st.title("🏃 Race Control Dashboard")

try:
    df = load_data()

    # Status-Logik
    gestartet = df[df['Start_Sec'] > 0]
    im_ziel = df[df['Ziel_Sec'] > 0]
    auf_strecke = df[(df['Start_Sec'] > 0) & (df['Ziel_Sec'] == 0)]

    # 1. Metriken im Datasport-Stil
    m1, m2, m3 = st.columns(3)
    m1.metric("Gestartet", len(gestartet))
    m2.metric("Im Ziel", len(im_ziel))
    m3.metric("Auf Strecke", len(auf_strecke))

    # 2. Visueller Fortschrittsbalken
    if len(gestartet) > 0:
        pct = len(im_ziel) / len(gestartet)
        st.write(f"**Gesamtfortschritt: {pct:.1%}**")
        st.progress(pct)

    # 3. Anomalie-Erkennung
    st.divider()
    st.subheader("⚠️ Auffälligkeiten (Nettozeit Analyse)")
    
    if len(im_ziel) > 1:
        avg_time = im_ziel['Netto_Sec'].mean()
        std_time = im_ziel['Netto_Sec'].std()
        
        # Markiere alle, die 2 Standardabweichungen schneller als der Schnitt sind
        # (Bei Triathlon München wäre eine Nettozeit < 1h bei Olympisch verdächtig)
        anomalies = im_ziel[im_ziel['Netto_Sec'] < (avg_time - 2 * std_time)]
        
        if not anomalies.empty:
            st.warning(f"{len(anomalies)} Teilnehmer sind ungewöhnlich schnell!")
            st.dataframe(anomalies[['Bib', 'Name', 'Startzeit', 'Zielzeit']])
        else:
            st.success("Keine auffälligen Schnellläufer erkannt.")

    # 4. Wer fehlt noch?
    with st.expander("Liste der Personen auf der Strecke"):
        st.table(auf_strecke[['Bib', 'Name', 'Startzeit']])

except Exception as e:
    st.error(f"Fehler: {e}. Prüfe, ob die API-Spalten 'Startzeit' und 'Zielzeit' heißen.")