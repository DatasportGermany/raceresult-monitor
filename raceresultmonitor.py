import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import time

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Race Track Monitor", layout="wide")

# --- HELPER FUNKTIONEN ---
def time_to_seconds(t_str):
    try:
        if not t_str or str(t_str).strip() in ["", "0", "00:00:00"]: 
            return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: 
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: 
            return int(parts[0]) * 60 + int(parts[1])
        return 0
    except:
        return 0

def render_competition(df, comp_name):
    """Zeigt an, wer noch auf der Strecke ist."""
    df.columns = [str(c).strip() for c in df.columns]
    
    # Filter: Nur reguläre Teilnehmer (Status == 0)
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)
    if status_col:
        df_active = df[df[status_col].astype(str).str.strip() == "0"].copy()
    else:
        df_active = df.copy()

    # Spalten finden
    bib_col = next((c for c in df.columns if 'bib' in c.lower() or 'stnr' in c.lower()), "Bib")
    name_col = next((c for c in df.columns if 'name' in c.lower()), "Name")
    start_col = next((c for c in df.columns if 'start' in c.lower()), None)
    goal_col = next((c for c in df.columns if 'ziel' in c.lower() or 'finish' in c.lower()), None)

    if start_col and goal_col:
        df_active['S_Sec'] = df_active[start_col].apply(time_to_seconds)
        df_active['G_Sec'] = df_active[goal_col].apply(time_to_seconds)

        # Logik: Gestartet aber keine Zielzeit
        auf_strecke = df_active[(df_active['S_Sec'] > 0) & (df_active['G_Sec'] == 0)]
        im_ziel = df_active[df_active['G_Sec'] > 0]
        
        with st.expander(f"🏆 {comp_name}", expanded=True):
            if not auf_strecke.empty:
                st.warning(f"⚠️ {len(auf_strecke)} Personen noch auf der Strecke")
                
                # Fortschrittsbalken
                total_started = len(im_ziel) + len(auf_strecke)
                progress = len(im_ziel) / total_started if total_started > 0 else 0
                st.progress(progress)
                
                # Tabelle der fehlenden Personen
                display_cols = [c for c in [bib_col, name_col, start_col] if c in df.columns]
                st.dataframe(auf_strecke[display_cols], use_container_width=True)
            else:
                st.success("✅ Alle Teilnehmer dieses Wettbewerbs sind im Ziel.")
    else:
        st.error(f"Spalten für Start/Ziel in '{comp_name}' nicht gefunden.")

def process_api(url, event_label):
    try:
        response = requests.get(url)
        json_data = response.json()
        
        if isinstance(json_data, dict) and 'data' in json_data:
            df = pd.DataFrame(json_data['data'], columns=json_data.get('columns', []))
        else:
            df = pd.DataFrame(json_data)
            
        df.columns = [str(c).strip() for c in df.columns]
        st.header(f"📍 Event: {event_label}")

        comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz']), None)

        if comp_col:
            for comp in df[comp_col].unique():
                render_competition(df[df[comp_col] == comp], comp)
        else:
            render_competition(df, "Gesamtklassement")
            
    except Exception as e:
        st.error(f"Fehler bei {event_label}: {e}")

# --- UI ---
st.sidebar.title("⚙️ Setup")
if 'events' not in st.session_state: st.session_state.events = []

with st.sidebar.form("api_form", clear_on_submit=True):
    name = st.text_input("Name des Rennens")
    url = st.text_input("API URL")
    if st.form_submit_button("Hinzufügen") and name and url:
        st.session_state.events.append({"name": name, "url": url})

if st.sidebar.button("Zurücksetzen"):
    st.session_state.events = []
    st.rerun()

refresh = st.sidebar.slider("Refresh (Sek.)", 10, 300, 30)

if not st.session_state.events:
    st.title("🏁 Race Track Monitor")
    st.info("Bitte API-URL in der Sidebar hinzufügen.")
else:
    for event in st.session_state.events:
        process_api(event['url'], event['name'])
    time.sleep(refresh)
    st.rerun()
