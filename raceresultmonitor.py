import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime
import time

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Race Control Tool", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e6ed; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNKTIONEN ---
def time_to_seconds(t_str):
    try:
        if not t_str or str(t_str).strip() == "" or str(t_str).strip() == "0": return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: # MM:SS
            return int(parts[0]) * 60 + int(parts[1])
        return 0
    except:
        return 0

# --- UI BEREICH ---
st.title("🏁 Multi-Race Control Center")

with st.expander("⚙️ API-Einstellungen", expanded=True):
    api_input = st.text_input("RaceResult API JSON URL:", placeholder="https://api.raceresult.com/...")
    col_btn1, col_btn2 = st.columns([1, 5])
    start_button = col_btn1.button("🚀 Analyse Starten")
    refresh_rate = st.sidebar.slider("Auto-Refresh (Sekunden)", 10, 300, 30)

# Session State initialisieren
if 'active_url' not in st.session_state:
    st.session_state.active_url = None

if start_button and api_input:
    st.session_state.active_url = api_input

# --- HAUPTLOGIK ---
if st.session_state.active_url:
    try:
        # Daten laden
        response = requests.get(st.session_state.active_url)
        json_data = response.json()
        df = pd.DataFrame(json_data['data'], columns=json_data['columns'])
        df.columns = [c.strip() for c in df.columns]

        # Spalten suchen
        start_col = next((c for c in df.columns if 'start' in c.lower()), None)
        goal_col = next((c for c in df.columns if 'ziel' in c.lower() or 'finish' in c.lower()), None)

        if start_col and goal_col:
            df['S_Sec'] = df[start_col].apply(time_to_seconds)
            df['G_Sec'] = df[goal_col].apply(time_to_seconds)
            df['Netto'] = df['G_Sec'] - df['S_Sec']

            # Kennzahlen
            gestartet = df[df['S_Sec'] > 0]
            im_ziel = df[df['G_Sec'] > 0]
            auf_strecke = df[(df['S_Sec'] > 0) & (df['G_Sec'] == 0)]

            m1, m2, m3 = st.columns(3)
            m1.metric("Gestartet", len(gestartet))
            m2.metric("Im Ziel", len(im_ziel))
            m3.metric("Auf Strecke", len(auf_strecke))

            # Grafik
            if len(gestartet) > 0:
                fig = go.Figure()
                fig.add_trace(go.Bar(x=[len(im_ziel)], name="Ziel", orientation='h', marker_color='#28a745'))
                fig.add_trace(go.Bar(x=[len(auf_strecke)], name="Strecke", orientation='h', marker_color='#ffc107'))
                fig.update_layout(barmode='stack', height=100, margin=dict(t=5, b=5, l=0, r=0), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            # Anomalien
            st.subheader("⚠️ Auffälligkeiten")
            if len(im_ziel) > 5:
                avg = im_ziel[im_ziel['Netto'] > 0]['Netto'].mean()
                std = im_ziel[im_ziel['Netto'] > 0]['Netto'].std()
                anomalies = im_ziel[(im_ziel['Netto'] > 0) & (im_ziel['Netto'] < (avg - 2 * std))]
                
                if not anomalies.empty:
                    st.error(f"Warnung: {len(anomalies)} Teilnehmer sind statistisch zu schnell!")
                    st.dataframe(anomalies)
                else:
                    st.success("Keine zeitlichen Anomalien gefunden.")
            
            st.subheader("Teilnehmer auf der Strecke")
            st.dataframe(auf_strecke, use_container_width=True)

        else:
            st.error(f"Spalten nicht gefunden. Gefundene Spalten: {list(df.columns)}")

    except Exception as e:
        st.error(f"Fehler bei der API-Abfrage: {e}")

    # Auto-Refresh Logik
    time.sleep(refresh_rate)
    st.rerun()
else:
    st.info("Bitte geben Sie oben einen API-Link ein und klicken Sie auf 'Analyse Starten'.")
