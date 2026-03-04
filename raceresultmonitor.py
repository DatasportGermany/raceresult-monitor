import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import time

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="RaceResult Pro Monitor", layout="wide")

# --- HELPER FUNKTIONEN ---
def time_to_seconds(t_str):
    """Wandelt HH:MM:SS oder MM:SS in Sekunden um."""
    try:
        if not t_str or str(t_str).strip() in ["", "0", "00:00:00"]: 
            return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: # MM:SS
            return int(parts[0]) * 60 + int(parts[1])
        return 0
    except:
        return 0

def render_competition(df, comp_name):
    """Analysiert einen gefilterten Datensatz eines Wettbewerbs."""
    # 1. Spaltennamen normalisieren (für Fehlertoleranz)
    df.columns = [str(c).strip() for c in df.columns]
    
    # 2. Status-Filter
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)
    if status_col:
        df[status_col] = df[status_col].astype(str).str.strip()
        df_clean = df[df[status_col] == "0"].copy()
    else:
        df_clean = df.copy() # Falls kein Status da ist, alle nehmen
    
    # 3. Dynamische Spaltensuche für die Anzeige und Berechnung
    # Wir suchen Spalten, die diese Begriffe enthalten
    bib_col = next((c for c in df.columns if 'bib' in c.lower() or 'stnr' in c.lower()), None)
    name_col = next((c for c in df.columns if 'name' in c.lower()), None)
    start_col = next((c for c in df.columns if 'start' in c.lower()), None)
    goal_col = next((c for c in df.columns if 'ziel' in c.lower() or 'finish' in c.lower()), None)

    # Prüfen, ob die kritischen Spalten da sind
    if start_col and goal_col:
        df_clean['S_Sec'] = df_clean[start_col].apply(time_to_seconds)
        df_clean['G_Sec'] = df_clean[goal_col].apply(time_to_seconds)
        df_clean['Netto'] = df_clean['G_Sec'] - df_clean['S_Sec']

        gestartet = df_clean[df_clean['S_Sec'] > 0]
        im_ziel = df_clean[df_clean['G_Sec'] > 0]
        auf_strecke = df_clean[(df_clean['S_Sec'] > 0) & (df_clean['G_Sec'] == 0)]
        
        with st.expander(f"🏆 {comp_name} | {len(im_ziel)} Finisher", expanded=True):
            # Nur Spalten anzeigen, die wir auch wirklich gefunden haben
            display_cols = [c for c in [bib_col, name_col, start_col, goal_col] if c is not None]
            
            # Anomalie-Check
            finisher_valid = im_ziel[im_ziel['Netto'] > 0]
            if len(finisher_valid) >= 5:
                avg = finisher_valid['Netto'].mean()
                std = finisher_valid['Netto'].std()
                anomalies = finisher_valid[finisher_valid['Netto'] < (avg - 2 * std)]
                
                if not anomalies.empty:
                    st.error(f"⚠️ {len(anomalies)} Anomalien gefunden!")
                    # Hier wird nur das angezeigt, was auch gefunden wurde
                    st.dataframe(anomalies[display_cols + ['Netto']], use_container_width=True)
                else:
                    st.success("✅ Alles im Normbereich")
            else:
                st.info("Warte auf Daten...")
    else:
        st.error(f"Fehler: Start- oder Zielspalte fehlt in '{comp_name}'. Gefundene Spalten: {list(df.columns)}")
def process_api(url, event_label):
    """Lädt Daten von der API und bereitet sie für das Dashboard auf."""
    try:
        response = requests.get(url)
        json_data = response.json()
        
        # Flexibles Laden je nach RaceResult JSON Struktur
        if isinstance(json_data, dict) and 'data' in json_data:
            cols = json_data.get('columns', [])
            df = pd.DataFrame(json_data['data'], columns=cols)
        else:
            df = pd.DataFrame(json_data)
            
        # Spaltennamen bereinigen
        df.columns = [str(c).strip() for c in df.columns]

        st.header(f"📍 Event: {event_label}")
        
        if df.empty:
            st.warning(f"Keine Teilnehmerdaten gefunden.")
            return

        # Wettbewerbs-Spalte finden (Wettbewerb, Event, Konkurrenz, etc.)
        comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)

        if comp_col:
            # Für jeden Wettbewerb eine eigene Sektion rendern
            for comp in df[comp_col].unique():
                comp_df = df[df[comp_col] == comp]
                render_competition(comp_df, comp)
        else:
            render_competition(df, "Gesamtklassement")
            
    except Exception as e:
        st.error(f"Fehler bei {event_label}: {e}")

# --- UI STRUKTUR ---
st.sidebar.title("⚙️ Race Control Setup")

# Liste der Events im Session State speichern
if 'events' not in st.session_state:
    st.session_state.events = []

# Formular zum Hinzufügen von APIs
with st.sidebar.form("api_form", clear_on_submit=True):
    name = st.text_input("Renn-Bezeichnung (z.B. Trollinger)")
    url = st.text_input("API URL (JSON)")
    submit = st.form_submit_button("Hinzufügen")
    if submit and name and url:
        st.session_state.events.append({"name": name, "url": url})

if st.sidebar.button("Alle Daten zurücksetzen"):
    st.session_state.events = []
    st.rerun()

refresh = st.sidebar.slider("Refresh Intervall (Sekunden)", 10, 300, 30)

# Main Loop (Dashboard Anzeige)
if not st.session_state.events:
    st.title("🏁 Race Monitor")
    st.info("Willkommen! Bitte fügen Sie in der Sidebar API-URLs hinzu, um das Monitoring zu starten.")
    st.markdown("""
    **Anleitung:**
    1. RaceResult Liste öffnen.
    2. Unter 'Integration' -> 'Einfache API' einen JSON-Export erstellen.
    3. URL kopieren und links einfügen.
    """)
else:
    # Alle registrierten Events nacheinander abarbeiten
    for event in st.session_state.events:
        process_api(event['url'], event['name'])
    
    # Wartezeit für Auto-Refresh
    time.sleep(refresh)
    st.rerun()
