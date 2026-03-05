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
    # Spaltennamen säubern
    df.columns = [str(c).strip() for c in df.columns]
    
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), None)
    name_col = next((c for c in df.columns if any(k in c.lower() for k in ['name', 'nachname', 'vorname'])), None)
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)

    time_keywords = ['start', 'km', 'split', 'mess', 'zwischen']
    # Chronologische Reihenfolge der Zeitspalten
    ordered_times = [c for c in df.columns if any(k in c.lower() for k in time_keywords) and c != goal_col] + [goal_col]

    if start_col and goal_col:
        # Aktuelle Zeit ermitteln
        now = datetime.now()
        now_sec = now.hour * 3600 + now.minute * 60 + now.second

        # Zeit-Spalten in Sekunden umwandeln
        for col in ordered_times:
            df[f'{col}_sec'] = df[col].apply(time_to_seconds)
        
        # Filter auf reguläre Teilnehmer
        df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy() if status_col else df.copy()
        auf_strecke = df_reg[(df_reg[f'{start_col}_sec'] > 0) & (df_reg[f'{goal_col}_sec'] == 0)].copy()
        
        st.subheader(f"🏆 {comp_name}")
        
        if not auf_strecke.empty:
            # --- SEKTOREN DURCHSCHNITTE BERECHNEN ---
            sector_averages = {}
            for i in range(len(ordered_times) - 1):
                col_a = ordered_times[i]
                col_b = ordered_times[i+1]
                finished_sector = df_reg[(df_reg[f'{col_a}_sec'] > 0) & (df_reg[f'{col_b}_sec'] > 0)]
                if not finished_sector.empty:
                    avg_duration = (finished_sector[f'{col_b}_sec'] - finished_sector[f'{col_a}_sec']).mean()
                    sector_averages[col_a] = avg_duration

            # --- INDIVIDUELLE ANALYSE ---
            def analyze_safety(row):
                last_point = start_col
                last_sec = row[f'{start_col}_sec']
                
                # Finde den spätesten Punkt, den der Läufer passiert hat
                for col_name in ordered_times:
                    if col_name != goal_col and row[f'{col_name}_sec'] > 0:
                        # Wir nehmen den Punkt mit dem höchsten Zeitwert (chronologisch am weitesten)
                        if row[f'{col_name}_sec'] >= last_sec:
                            last_point = col_name
                            last_sec = row[f'{col_name}_sec']
                
                # Zeit seit letztem Kontakt
                time_diff_sec = max(0, now_sec - last_sec)
                time_since_last_contact = time_diff_sec / 60
                
                # Sektor-Vergleich
                avg_sec = sector_averages.get(last_point, 3600) 
                avg_min = avg_sec / 60
                
                # Warnschwelle 150% (50% langsamer als Schnitt)
                is_overdue = time_since_last_contact > (avg_min * 1.5)
                
                status_text = f"{int(time_since_last_contact)} Min seit {last_point}"
                if is_overdue:
                    status_text = f"🚩 {status_text} (Schnitt: {int(avg_min)} Min)"
                
                return pd.Series({
                    'Letzter Kontakt': last_point, 
                    'Sicherheits-Status': status_text, 
                    'Sort_Min': time_since_last_contact
                })

            # Neue Spalten berechnen
            new_cols = auf_strecke.apply(analyze_safety, axis=1)
            auf_strecke = pd.concat([auf_strecke, new_cols], axis=1)
            
            # Anzeige-Filter
            display_list = [c for c in [bib_col, name_col, 'Letzter Kontakt', 'Sicherheits-Status'] if c in auf_strecke.columns]
            
            st.warning(f"⚠️ {len(auf_strecke)} Teilnehmer auf der Strecke")
            
            # Sicherer Sortier-Vorgang
            if 'Sort_Min' in auf_strecke.columns:
                auf_strecke = auf_strecke.sort_values(by='Sort_Min', ascending=False)
            
            st.dataframe(
                auf_strecke[display_list], 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.success("✅ Alle regulär gestarteten Teilnehmer sind im Ziel.")
    else:
        st.error(f"Spaltenfehler: Start- oder Zielspalte konnte nicht identifiziert werden.")
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