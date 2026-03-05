import streamlit as st
import pandas as pd
import requests
import time

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Race Management Pro", layout="wide")

# --- HELPER FUNKTIONEN ---
def time_to_seconds(t_str):
    try:
        if not t_str or str(t_str).strip() in ["", "0", "00:00:00", "None", "nan"]: 
            return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
        return 0
    except: return 0

def is_empty(val):
    v = str(val).strip().lower()
    return v in ["", "none", "nan", "0", "00:00:00"]

def render_competition(df, comp_name):
    """Sicherheits-Check: Start vorhanden, Ziel leer?"""
    df.columns = [str(c).strip() for c in df.columns]
    
    # Dynamische Spalten-Zuordnung für deine API
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), "Startnummer")
    name_col = next((c for c in df.columns if 'name' in c.lower()), "Name")
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), "Status")

    if start_col and goal_col:
        df['S_Sec'] = df[start_col].apply(time_to_seconds)
        df['G_Sec'] = df[goal_col].apply(time_to_seconds)

        # Filter auf Status 0 (regulär unterwegs)
        df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy()

        # Logik für Personen auf der Strecke
        auf_strecke = df_reg[(df_reg['S_Sec'] > 0) & (df_reg[goal_col].apply(is_empty))]
        im_ziel = df_reg[(df_reg['S_Sec'] > 0) & (~df_reg[goal_col].apply(is_empty))]
        
        with st.expander(f"🏆 {comp_name}", expanded=True):
            if not auf_strecke.empty:
                st.warning(f"🔔 {len(auf_strecke)} Teilnehmer noch auf der Strecke")
                total = len(im_ziel) + len(auf_strecke)
                st.progress(len(im_ziel) / total if total > 0 else 0)
                
                disp = [c for c in [bib_col, name_col, start_col] if c in df_reg.columns]
                st.dataframe(auf_strecke[disp], use_container_width=True, hide_index=True)
            else:
                if not im_ziel.empty:
                    st.success(f"✅ Alle {len(im_ziel)} Teilnehmer sind im Ziel.")
                else:
                    st.info("Warten auf Starts...")
    else:
        st.error(f"Spaltenfehler in '{comp_name}'. Erkannt: Start='{start_col}', Ziel='{goal_col}'")

# --- APP NAVIGATION ---
if 'event_store' not in st.session_state:
    st.session_state.event_store = []

# Sidebar Navigation
mode = st.sidebar.radio("Navigation", ["📊 Dashboard", "⚙️ API Verwaltung"])

# --- MODUS: API VERWALTUNG ---
if mode == "⚙️ API Verwaltung":
    st.title("⚙️ API Verwaltung")
    st.write("Hier kannst du neue Renn-APIs hinzufügen oder bestehende löschen.")
    
    with st.form("new_event", clear_on_submit=True):
        new_name = st.text_input("Name des Events (z.B. Trollinger)")
        new_url = st.text_input("RaceResult JSON URL")
        if st.form_submit_button("Event hinzufügen"):
            if new_name and new_url:
                st.session_state.event_store.append({"name": new_name, "url": new_url})
                st.success(f"Event '{new_name}' hinzugefügt!")
            else:
                st.error("Bitte Name und URL ausfüllen.")

    if st.session_state.event_store:
        st.subheader("Gespeicherte Events")
        for i, ev in enumerate(st.session_state.event_store):
            col1, col2 = st.columns([4, 1])
            col1.write(f"**{ev['name']}**: {ev['url'][:50]}...")
            if col2.button("Löschen", key=f"del_{i}"):
                st.session_state.event_store.pop(i)
                st.rerun()

# --- MODUS: DASHBOARD ---
elif mode == "📊 Dashboard":
    st.title("📊 Race Monitor Dashboard")

    if not st.session_state.event_store:
        st.info("Keine Events konfiguriert. Bitte wechsle zur 'API Verwaltung'.")
    else:
        # Dropdown Auswahl des Events
        event_names = [e['name'] for e in st.session_state.event_store]
        selected_event_name = st.selectbox("Wähle ein Event zur Überwachung:", event_names)
        
        # Hol die URL zum ausgewählten Namen
        selected_url = next(e['url'] for e in st.session_state.event_store if e['name'] == selected_event_name)
        
        refresh_rate = st.sidebar.slider("Auto-Refresh (Sekunden)", 10, 300, 30)
        
        # Daten laden und anzeigen
        try:
            res = requests.get(selected_url, timeout=10)
            json_data = res.json()
            if isinstance(json_data, dict) and 'data' in json_data:
                df = pd.DataFrame(json_data['data'], columns=json_data.get('columns', []))
            else:
                df = pd.DataFrame(json_data)
            
            # Wettbewerbs-Trennung
            comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz']), None)
            
            if comp_col:
                for comp in df[comp_col].unique():
                    render_competition(df[df[comp_col] == comp], str(comp))
            else:
                render_competition(df, selected_event_name)
                
            # Auto-Refresh
            time.sleep(refresh_rate)
            st.rerun()
            
        except Exception as e:
            st.error(f"Fehler beim Laden des Events: {e}")