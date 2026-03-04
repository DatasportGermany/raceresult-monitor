import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import time

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="RaceResult Pro Monitor", layout="wide")

# --- HELPER FUNKTIONEN ---
def time_to_seconds(t_str):
    try:
        if not t_str or str(t_str).strip() in ["", "0", "00:00:00"]: return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
        return 0
    except: return 0

def render_competition(df, comp_name):
    """Analysiert einen gefilterten Datensatz eines Wettbewerbs"""
    # 1. Filter: Nur reguläre Teilnehmer für die Statistik (Status == 0 oder "0")
    # Wir stellen sicher, dass Status numerisch verglichen wird
    df['Status'] = df['Status'].astype(str).str.strip()
    df_clean = df[df['Status'] == "0"].copy()
    
    # 2. Zeit-Spalten finden
    start_col = next((c for c in df.columns if 'start' in c.lower()), None)
    goal_col = next((c for c in df.columns if 'ziel' in c.lower() or 'finish' in c.lower()), None)

    if start_col and goal_col:
        df_clean['S_Sec'] = df_clean[start_col].apply(time_to_seconds)
        df_clean['G_Sec'] = df_clean[goal_col].apply(time_to_seconds)
        df_clean['Netto'] = df_clean['G_Sec'] - df_clean['S_Sec']

        # Status Gruppen
        gestartet = df_clean[df_clean['S_Sec'] > 0]
        im_ziel = df_clean[df_clean['G_Sec'] > 0]
        auf_strecke = df_clean[(df_clean['S_Sec'] > 0) & (df_clean['G_Sec'] == 0)]
        
        # UI Anzeige
        with st.expander(f"🏆 {comp_name} | {len(im_ziel)} im Ziel | {len(auf_strecke)} auf Strecke", expanded=False):
            c1, c2 = st.columns([1, 3])
            
            with c1:
                st.metric("Aktiv auf Strecke", len(auf_strecke))
                dnf_count = len(df[df['Status'].str.lower().isin(['dnf', 'dsq', '1', '2'])]) # Status != 0
                if dnf_count > 0:
                    st.caption(f"🚫 {dnf_count} Teilnehmer (DNF/DSQ) ignoriert")

            with c2:
                # Anomalie-Erkennung (Z-Score)
                # Wir nehmen nur valide Nettozeiten > 0
                finisher_valid = im_ziel[im_ziel['Netto'] > 0]
                if len(finisher_valid) >= 5:
                    avg = finisher_valid['Netto'].mean()
                    std = finisher_valid['Netto'].std()
                    
                    # Markierung: Mehr als 2 Standardabweichungen schneller als der Schnitt
                    anomalies = finisher_valid[finisher_valid['Netto'] < (avg - 2 * std)]
                    
                    if not anomalies.empty:
                        st.error(f"⚠️ {len(anomalies)} verdächtig schnelle Zeiten erkannt!")
                        st.dataframe(anomalies[['Bib', 'Name', start_col, goal_col, 'Netto']], use_container_width=True)
                    else:
                        st.success("✅ Zeiten liegen im statistischen Normbereich.")
                else:
                    st.info("Sammle Daten für statistische Analyse...")

def process_api(url, event_label):
    try:
        response = requests.get(url)
        json_data = response.json()
        df = pd.DataFrame(json_data['data'], columns=json_data['columns'])
        df.columns = [c.strip() for c in df.columns]

        st.header(f"📍 Event: {event_label}")

        # Automatische Trennung nach Wettbewerb (falls vorhanden)
        comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz']), None)

        if comp_col:
            for comp in df[comp_col].unique():
                comp_df = df[df[comp_col] == comp]
                render_competition(comp_df, comp)
        else:
            render_competition(df, "Gesamtklassement")
            
    except Exception as e:
        st.error(f"Fehler bei {event_label}: {e}")

# --- UI STRUKTUR ---
st.sidebar.title("⚙️ Race Control Setup")

if 'events' not in st.session_state:
    st.session_state.events = []

with st.sidebar.form("api_form"):
    name = st.text_input("Renn-Bezeichnung")
    url = st.text_input("API URL (JSON)")
    submit = st.form_submit_button("Hinzufügen")
    if submit and name and url:
        st.session_state.events.append({"name": name, "url": url})

if st.sidebar.button("Alle Daten zurücksetzen"):
    st.session_state.events = []
    st.rerun()

refresh = st.sidebar.slider("Refresh (Sekunden)", 10, 120, 30)

# Main Loop
if not st.session_state.events:
    st.title("🏁 Willkommen beim Race Monitor")
    st.info("Bitte fügen Sie in der Sidebar die API-URLs Ihrer RaceResult Listen hinzu.")
else:
    for event in st.session_state.events:
        process_api(event['url'], event['name'])
    
    time.sleep(refresh)
    st.rerun()
