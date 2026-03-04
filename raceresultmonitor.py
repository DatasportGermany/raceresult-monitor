import streamlit as st
import pandas as pd
import requests
import time

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Race Monitor - Safety Track", layout="wide")

# --- HELPER FUNKTIONEN ---
def time_to_seconds(t_str):
    """Wandelt Zeit-Strings in Sekunden um. Gibt 0 bei leeren/ungültigen Werten."""
    try:
        if not t_str or str(t_str).strip() in ["", "0", "00:00:00", "None", "nan"]: 
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
    """Sicherheits-Check: Wer hat ein Start-Signal, aber kein Ziel-Signal?"""
    df.columns = [str(c).strip() for c in df.columns]
    
    # 1. Spalten-Zuordnung basierend auf deinem JSON-Ausschnitt
    # Wir suchen nach 'Startnummer', 'Start', 'Ziel' und 'Status'
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), "Startnummer")
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), "Status")

    if start_col and goal_col:
        # Umwandlung in Sekunden zur Berechnung
        df['S_Sec'] = df[start_col].apply(time_to_seconds)
        df['G_Sec'] = df[goal_col].apply(time_to_seconds)

        # Filter auf Status 0 (regulär)
        df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy()

        # DIE KORRIGIERTE LOGIK:
        # Ein Teilnehmer ist auf der Strecke, wenn:
        # 1. Er eine Startzeit hat (S_Sec > 0)
        # 2. Die Zielzeit absolut leer ist (None, NaN oder leerer String)
        
        def is_empty(val):
            v = str(val).strip().lower()
            return v in ["", "none", "nan", "0", "00:00:00"]

        auf_strecke = df_reg[
            (df_reg['S_Sec'] > 0) & 
            (df_reg[goal_col].apply(is_empty))
        ]
        
        im_ziel = df_reg[
            (df_reg['S_Sec'] > 0) & 
            (~df_reg[goal_col].apply(is_empty))
        ]
        
        with st.expander(f"🏆 {comp_name}", expanded=True):
            if not auf_strecke.empty:
                st.warning(f"🔔 {len(auf_strecke)} Teilnehmer noch auf der Strecke")
                
                # Fortschrittsbalken
                total = len(im_ziel) + len(auf_strecke)
                st.progress(len(im_ziel) / total if total > 0 else 0)
                
                # Anzeige der Liste
                disp = [c for c in [bib_col, "Name", start_col] if c in df_reg.columns]
                st.dataframe(auf_strecke[disp], use_container_width=True, hide_index=True)
            else:
                if not im_ziel.empty:
                    st.success(f"✅ Alle {len(im_ziel)} Teilnehmer sind im Ziel.")
                else:
                    st.info("Noch keine Starts erfasst.")
    else:
        st.error(f"Spalten nicht gefunden. Erkannt: Start='{start_col}', Ziel='{goal_col}'")

def process_api(url, event_label):
    """Lädt Daten und trennt nach Wettbewerben."""
    try:
        response = requests.get(url, timeout=15)
        json_data = response.json()
        
        # Daten-Struktur von RaceResult verarbeiten
        if isinstance(json_data, dict) and 'data' in json_data:
            df = pd.DataFrame(json_data['data'], columns=json_data.get('columns', []))
        else:
            df = pd.DataFrame(json_data)
            
        df.columns = [str(c).strip() for c in df.columns]
        st.header(f"📍 Event: {event_label}")

        # Prüfen, ob Wettbewerbe unterschieden werden müssen
        comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)

        if comp_col:
            for comp in df[comp_col].unique():
                render_competition(df[df[comp_col] == comp], str(comp))
        else:
            render_competition(df, "Gesamtklassement")
            
    except Exception as e:
        st.error(f"Fehler beim Laden von '{event_label}': {e}")

# --- UI HAUPTTEIL ---
st.sidebar.title("⚙️ Setup & Monitor")

if 'events' not in st.session_state:
    st.session_state.events = []

with st.sidebar.form("api_form", clear_on_submit=True):
    name = st.text_input("Name des Rennens (z.B. Triathlon München)")
    url = st.text_input("RaceResult JSON URL")
    if st.form_submit_button("Hinzufügen") and name and url:
        st.session_state.events.append({"name": name, "url": url})

if st.sidebar.button("Alle Rennen löschen"):
    st.session_state.events = []
    st.rerun()

refresh = st.sidebar.slider("Auto-Refresh (Sekunden)", 10, 300, 30)

# --- DASHBOARD RENDERING ---
if not st.session_state.events:
    st.title("🏁 Race Track Monitor")
    st.info("Willkommen! Bitte fügen Sie links eine API-URL aus RaceResult hinzu, um das Live-Tracking zu starten.")
    st.markdown("""
    **Voraussetzung für die API-Liste:**
    Die Liste muss folgende Felder enthalten: 
    - `Bib` (Startnummer)
    - `Name`
    - `Status` (0 = OK)
    - `Startzeit`
    - `Zielzeit`
    """)
else:
    # Alle Events in der Liste verarbeiten
    for event in st.session_state.events:
        process_api(event['url'], event['name'])
    
    # Wartezeit für Refresh (verhindert 'schwarzen Bildschirm' durch zu schnelles Neuladen)
    time.sleep(refresh)
    st.rerun()
