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
    """Sicherheits-Analyse: Wer ist statistisch überfällig (Pace-basiert)?"""
    df.columns = [str(c).strip() for c in df.columns]
    
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), None)
    name_col = next((c for c in df.columns if any(k in c.lower() for k in ['name', 'nachname', 'vorname'])), None)
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)

    time_keywords = ['start', 'km', 'split', 'mess', 'zwischen']
    # Wichtig: Die Zeitspalten müssen in der API in der richtigen chronologischen Reihenfolge stehen!
    ordered_times = [c for c in df.columns if any(k in c.lower() for k in time_keywords) and c != goal_col] + [goal_col]

    if start_col and goal_col:
        now_sec = datetime.now().hour * 3600 + datetime.now().minute * 60 + datetime.now().second

        for col in ordered_times:
            df[f'{col}_sec'] = df[col].apply(time_to_seconds)
        
        df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy() if status_col else df.copy()
        auf_strecke = df_reg[(df_reg[f'{start_col}_sec'] > 0) & (df_reg[f'{goal_col}_sec'] == 0)].copy()
        im_ziel = df_reg[df_reg[f'{goal_col}_sec'] > 0].copy()
        
        st.subheader(f"🏆 {comp_name}")
        
        if not auf_strecke.empty:
            # --- SEKTOREN DURCHSCHNITTE BERECHNEN ---
            # Wir berechnen, wie lange man im Schnitt von Punkt A nach Punkt B braucht
            sector_averages = {}
            for i in range(len(ordered_times) - 1):
                col_a = ordered_times[i]
                col_b = ordered_times[i+1]
                # Nur Teilnehmer, die beide Punkte passiert haben
                finished_sector = df_reg[(df_reg[f'{col_a}_sec'] > 0) & (df_reg[f'{col_b}_sec'] > 0)]
                if not finished_sector.empty:
                    avg_duration = (finished_sector[f'{col_b}_sec'] - finished_sector[f'{col_a}_sec']).mean()
                    sector_averages[col_a] = avg_duration

            # --- INDIVIDUELLE ANALYSE ---
            def analyze_safety(row):
                # Finde den letzten Messpunkt
                last_point = start_col
                next_point = goal_col
                last_sec = row[f'{start_col}_sec']
                
                for i in range(len(ordered_times) - 1):
                    if row[f'{ordered_times[i]}_sec'] > 0:
                        last_point = ordered_times[i]
                        next_point = ordered_times[i+1]
                        last_sec = row[f'{ordered_times[i]}_sec']
                
                time_since_last_contact = (now_sec - last_sec) / 60
                
                # Hol den Durchschnitt für diesen Sektor (wenn vorhanden)
                avg_sec = sector_averages.get(last_point, 3600) # Fallback 60 Min
                avg_min = avg_sec / 60
                
                # Flagge wenn: Zeit seit letztem Kontakt > 1.5 * Durchschnittszeit des Sektors
                is_overdue = time_since_last_contact > (avg_min * 1.5)
                
                status_text = f"{int(time_since_last_contact)} Min seit {last_point}"
                if is_overdue:
                    status_text = f"🚩 {status_text} (Schnitt: {int(avg_min)} Min)"
                
                return pd.Series([last_point, status_text, time_since_last_contact])

            auf_strecke[['Letzter Kontakt', 'Sicherheits-Status', 'Sort_Min']] = auf_strecke.apply(analyze_safety, axis=1)
            
            display_list = [c for c in [bib_col, name_col, 'Letzter Kontakt', 'Sicherheits-Status'] if c is not None]
            st.warning(f"⚠️ {len(auf_strecke)} Teilnehmer auf der Strecke")
            st.dataframe(
                auf_strecke[display_list].sort_values(by='Sort_Min', ascending=False), 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.success("✅ Alle Teilnehmer im Ziel.")

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