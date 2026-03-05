import streamlit as st
import pandas as pd
import requests
import time
import urllib.parse
import json
import os
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
st.set_page_config(page_title="Race Safety Monitor", layout="wide")

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

# --- RENDER LOGIK ---
def render_competition(df, comp_name):
    """Sicherheits-Analyse: Wer ist wie lange überfällig?"""
    df.columns = [str(c).strip() for c in df.columns]
    
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), None)
    name_col = next((c for c in df.columns if any(k in c.lower() for k in ['name', 'nachname', 'vorname'])), None)
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)

    time_keywords = ['start', 'km', 'split', 'mess', 'zwischen']
    split_cols = [c for c in df.columns if any(k in c.lower() for k in time_keywords) and c != goal_col]

    if start_col and goal_col:
        # Aktuelle Uhrzeit in Sekunden seit Tagesbeginn für Überfällig-Check
        now = datetime.now()
        now_sec = now.hour * 3600 + now.minute * 60 + now.second

        for col in split_cols + [goal_col]:
            df[f'{col}_sec'] = df[col].apply(time_to_seconds)
        
        df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy() if status_col else df.copy()

        auf_strecke = df_reg[(df_reg[f'{start_col}_sec'] > 0) & (df_reg[f'{goal_col}_sec'] == 0)].copy()
        
        st.subheader(f"🏆 {comp_name}")
        
        if not auf_strecke.empty:
            # --- SICHERHEITS-LOGIK (ÜBERFÄLLIG) ---
            split_cols_sec = [f'{c}_sec' for c in split_cols]
            auf_strecke['Last_Time_Sec'] = auf_strecke[split_cols_sec].max(axis=1)
            
            # Berechnung: Wie viele Minuten seit letztem Kontakt vergangen?
            auf_strecke['Seit_Kontakt_Min'] = (now_sec - auf_strecke['Last_Time_Sec']) / 60
            
            def get_last_point_name(row):
                best_col = start_col
                max_s = 0
                for c in split_cols:
                    if row[f'{c}_sec'] > max_s:
                        max_s = row[f'{c}_sec']
                        best_col = c
                return best_col

            auf_strecke['Letzter Kontakt'] = auf_strecke.apply(get_last_point_name, axis=1)
            
            # Status-Text mit Warn-Flagge bei > 30 Min
            def format_overdue(min_val):
                if min_val < 0: return "Zeitfehler (Zukunft)"
                if min_val > 30: return f"🚩 {int(min_val)} Min überfällig"
                return f"{int(min_val)} Min unterwegs"

            auf_strecke['Status / Überfällig'] = auf_strecke['Seit_Kontakt_Min'].apply(format_overdue)
            
            # Anzeige-Tabelle
            display_list = [c for c in [bib_col, name_col, 'Letzter Kontakt', 'Status / Überfällig'] if c is not None]
            st.warning(f"⚠️ {len(auf_strecke)} Teilnehmer auf der Strecke")
            st.dataframe(
                auf_strecke[display_list].sort_values(by='Seit_Kontakt_Min', ascending=False), 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.success("✅ Alle Teilnehmer im Ziel oder noch nicht gestartet.")
    else:
        st.error(f"Spaltenfehler: Start oder Ziel nicht erkannt.")

# --- DASHBOARD & NAVIGATION ---
def run_dashboard(event_obj):
    if not st.query_params.get("event"):
        refresh_rate = st.sidebar.slider("Auto-Refresh (s)", 10, 300, 30)
    else:
        refresh_rate = 30

    try:
        res = requests.get(event_obj['url'], timeout=10)
        json_data = res.json()
        df = pd.DataFrame(json_data['data'], columns=json_data.get('columns', [])) if 'data' in json_data else pd.DataFrame(json_data)
        
        df.columns = [str(c).strip() for c in df.columns]
        comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz']), None)
        
        if comp_col:
            for comp in df[comp_col].unique():
                render_competition(df[df[comp_col] == comp], str(comp))
                st.divider()
        else:
            render_competition(df, event_obj['name'])
            
        time.sleep(refresh_rate)
        st.rerun()
    except Exception as e:
        st.error(f"Fehler: {e}")

all_events = load_events()
public_event_name = st.query_params.get("event")

if public_event_name:
    st.title(f"🚨 Safety Monitor: {public_event_name}")
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
                save_events(all_events); st.rerun()
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