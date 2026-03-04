import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import time

st.set_page_config(page_title="Multi-Race Monitor", layout="wide")

# --- HELPER FUNKTIONEN ---
def time_to_seconds(t_str):
    try:
        if not t_str or str(t_str).strip() in ["", "0"]: return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
        return 0
    except: return 0

def process_event(url, event_name):
    """Verarbeitet ein einzelnes Event und gibt das UI aus."""
    try:
        response = requests.get(url)
        json_data = response.json()
        df = pd.DataFrame(json_data['data'], columns=json_data['columns'])
        df.columns = [c.strip() for c in df.columns]

        # Spalten-Erkennung
        start_col = next((c for c in df.columns if 'start' in c.lower()), None)
        goal_col = next((c for c in df.columns if 'ziel' in c.lower() or 'finish' in c.lower()), None)

        if start_col and goal_col:
            df['S_Sec'] = df[start_col].apply(time_to_seconds)
            df['G_Sec'] = df[goal_col].apply(time_to_seconds)
            df['Netto'] = df['G_Sec'] - df['S_Sec']

            gestartet = df[df['S_Sec'] > 0]
            im_ziel = df[df['G_Sec'] > 0]
            auf_strecke = df[(df['S_Sec'] > 0) & (df['G_Sec'] == 0)]

            # UI Karte für das Event
            with st.expander(f"📊 {event_name} (Gestartet: {len(gestartet)} | Ziel: {len(im_ziel)})", expanded=True):
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.metric("Auf Strecke", len(auf_strecke))
                    # Kleiner Fortschrittsbalken
                    if len(gestartet) > 0:
                        progress = len(im_ziel) / len(gestartet)
                        st.progress(progress)
                
                with col2:
                    # Anomalien-Check
                    if len(im_ziel) > 5:
                        avg = im_ziel[im_ziel['Netto'] > 0]['Netto'].mean()
                        std = im_ziel[im_ziel['Netto'] > 0]['Netto'].std()
                        anomalies = im_ziel[(im_ziel['Netto'] > 0) & (im_ziel['Netto'] < (avg - 2 * std))]
                        
                        if not anomalies.empty:
                            st.error(f"⚠️ {len(anomalies)} Anomalien gefunden!")
                            st.dataframe(anomalies[['Bib', 'Name', goal_col]], height=150)
                        else:
                            st.success("✅ Keine Anomalien")
                    else:
                        st.info("Warte auf mehr Finisher für Analyse...")
        else:
            st.error(f"Spalten in {event_name} nicht erkannt.")
    except Exception as e:
        st.error(f"Fehler bei {event_name}: {e}")

# --- UI STRUKTUR ---
st.title("🌐 Multi-Race Control Center")

# Sidebar für Management
st.sidebar.header("Rennen verwalten")
if 'event_list' not in st.session_state:
    st.session_state.event_list = []

with st.sidebar.form("add_event"):
    new_name = st.text_input("Name des Rennens (z.B. Mitteldistanz)")
    new_url = st.text_input("RaceResult JSON URL")
    add_btn = st.form_submit_button("Hinzufügen")
    
    if add_btn and new_name and new_url:
        st.session_state.event_list.append({"name": new_name, "url": new_url})

if st.sidebar.button("Liste löschen"):
    st.session_state.event_list = []
    st.rerun()

refresh_rate = st.sidebar.slider("Auto-Refresh (s)", 10, 300, 30)

# --- HAUPTANZEIGE ---
if not st.session_state.event_list:
    st.info("Fügen Sie in der Sidebar Rennen hinzu, um das Monitoring zu starten.")
else:
    # Dashboards für alle Events rendern
    for event in st.session_state.event_list:
        process_event(event['url'], event['name'])
    
    # Auto-Refresh
    time.sleep(refresh_rate)
    st.rerun()
