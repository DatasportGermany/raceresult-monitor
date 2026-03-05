import streamlit as st
import pandas as pd
import requests
import time
import urllib.parse
import json
import os
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- DATEI-PFAD FÜR SPEICHERUNG ---
DB_FILE = "event_db.json"

# --- HELPER FÜR DATENBANK ---
def load_events():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except: return []
    return []

def save_events(events):
    with open(DB_FILE, "w") as f:
        json.dump(events, f)

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Race Monitor Pro + Predictor", layout="wide")

# --- ZEIT-HELPER ---
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

# --- RENDER LOGIK ---
def render_competition(df, comp_name):
    """Dynamische Analyse mit Zwischenzeiten (Splits)"""
    # Spaltennamen säubern
    df.columns = [str(c).strip() for c in df.columns]
    
    # 1. Dynamische Spalten-Identifikation (Fuzzy)
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), None)
    # Suche nach Name, Nachname oder Vorname
    name_col = next((c for c in df.columns if any(k in c.lower() for k in ['name', 'nachname', 'vorname'])), None)
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)

    # Identifiziere alle Zeit-Spalten für die Split-Logik
    # Wir nehmen alles, was nach Zeit aussieht, außer das Ziel (für die Prognose)
    time_keywords = ['start', 'km', 'split', 'mess', 'zwischen']
    split_cols = [c for c in df.columns if any(k in c.lower() for k in time_keywords) and c != goal_col]

    if start_col and goal_col:
        # Hilfs-Spalten für Sekunden erstellen (nur für valide Zeitspalten)
        all_time_cols = split_cols + [goal_col]
        for col in all_time_cols:
            df[f'{col}_sec'] = df[col].apply(time_to_seconds)
        
        # Status Filter
        if status_col:
            df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy()
        else:
            df_reg = df.copy()

        # Wer ist im Ziel?
        im_ziel = df_reg[df_reg[f'{goal_col}_sec'] > 0].copy()
        # Wer ist auf der Strecke?
        auf_strecke = df_reg[(df_reg[f'{start_col}_sec'] > 0) & (df_reg[f'{goal_col}_sec'] == 0)].copy()
        
        st.subheader(f"🏆 {comp_name}")
        
        if not auf_strecke.empty:
            # --- SPLIT LOGIK ---
            # Finde den letzten Messpunkt für jeden Läufer
            split_cols_sec = [f'{c}_sec' for c in split_cols]
            auf_strecke['Last_Time_Sec'] = auf_strecke[split_cols_sec].max(axis=1)
            
            # ETA Berechnung (wenn Finisher da sind)
            if not im_ziel.empty:
                avg_total_time = (im_ziel[f'{goal_col}_sec'] - im_ziel[f'{start_col}_sec']).mean()
                # Prognose: Aktuelle Zeit + geschätzte Restzeit
                auf_strecke['ETA_Sec'] = auf_strecke['Last_Time_Sec'] + (avg_total_time - (auf_strecke['Last_Time_Sec'] - auf_strecke[f'{start_col}_sec']))
            else:
                auf_strecke['ETA_Sec'] = 0

            # --- UI LAYOUT ---
            col_t, col_g = st.columns([1, 1])
            
            with col_t:
                st.warning(f"🔔 {len(auf_strecke)} Teilnehmer auf der Strecke")
                
                # Bestimme den Namen des letzten Messpunkts als Text
                def get_last_point_name(row):
                    best_col = start_col
                    max_s = 0
                    for c in split_cols:
                        if row[f'{c}_sec'] > max_s:
                            max_s = row[f'{c}_sec']
                            best_col = c
                    return best_col

                auf_strecke['Letzter Messpunkt'] = auf_strecke.apply(get_last_point_name, axis=1)
                
                # Erstelle Liste der verfügbaren Anzeige-Spalten (verhindert 'Key Error')
                display_list = [c for c in [bib_col, name_col, 'Letzter Messpunkt'] if c is not None]
                st.dataframe(auf_strecke[display_list], use_container_width=True, hide_index=True)

            with col_g:
                if not im_ziel.empty:
                    # Histogramm-Erstellung
                    auf_strecke['ETA_Bin'] = auf_strecke['ETA_Sec'].apply(lambda x: (datetime(20

def run_dashboard(event_obj):
    refresh_rate = 30
    if not st.query_params.get("event"):
        refresh_rate = st.sidebar.slider("Auto-Refresh (s)", 10, 300, 30)

    try:
        res = requests.get(event_obj['url'], timeout=10)
        json_data = res.json()
        
        if isinstance(json_data, dict) and 'data' in json_data:
            df = pd.DataFrame(json_data['data'], columns=json_data.get('columns', []))
        elif isinstance(json_data, list):
            df = pd.DataFrame(json_data)
        else: return

        df.columns = [str(c).strip() for c in df.columns]
        
        comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)
        
        if comp_col:
            for comp in df[comp_col].unique():
                render_competition(df[df[comp_col] == comp], str(comp))
                st.divider()
        else:
            render_competition(df, event_obj['name'])
            
        time.sleep(refresh_rate)
        st.rerun()
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")

# --- APP FLOW ---
all_events = load_events()
public_event_name = st.query_params.get("event")

if public_event_name:
    st.title(f"📊 Live-Monitor: {public_event_name}")
    selected_event = next((e for e in all_events if e['name'] == public_event_name), None)
    if selected_event: run_dashboard(selected_event)
    else: st.error("Event nicht gefunden.")
else:
    mode = st.sidebar.radio("Navigation", ["📊 Dashboard", "⚙️ API Verwaltung"])

    if mode == "⚙️ API Verwaltung":
        st.title("⚙️ API Verwaltung")
        with st.form("new_event", clear_on_submit=True):
            n = st.text_input("Event Name")
            u = st.text_input("RaceResult URL (JSON)")
            if st.form_submit_button("Hinzufügen"):
                all_events.append({"name": n, "url": u})
                save_events(all_events)
                st.rerun()

        for i, ev in enumerate(all_events):
            c1, c2 = st.columns([4, 1])
            share_url = f"/?event={urllib.parse.quote(ev['name'])}"
            c1.write(f"**{ev['name']}**")
            c1.code(share_url, language="text")
            if c2.button("Löschen", key=f"del_{i}"):
                all_events.pop(i); save_events(all_events); st.rerun()

    elif mode == "📊 Dashboard":
        if not all_events: st.info("Keine Events angelegt.")
        else:
            sel_name = st.selectbox("Event wählen", [e['name'] for e in all_events])
            run_dashboard(next(e for e in all_events if e['name'] == sel_name))