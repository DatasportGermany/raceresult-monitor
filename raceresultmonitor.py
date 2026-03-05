import streamlit as st
import pandas as pd
import requests
import time
import urllib.parse
import json
import os
from datetime import datetime, timedelta

# --- DATENBANK & KONFIGURATION ---
DB_FILE = "event_db.json"

def load_events():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return []
    return []

def save_events(events):
    with open(DB_FILE, "w") as f: json.dump(events, f)

# --- MODERNES DATASPORT-DESIGN (CSS) ---
def apply_custom_design():
    st.markdown("""
        <style>
        /* Hintergrund und Schrift */
        .stApp { background-color: #f4f7f9 !important; }
        
        /* Überschriften-Farbe fixieren */
        h1, h2, h3 { color: #003366 !important; font-family: 'Segoe UI', Roboto, sans-serif; }
        
        /* Sidebar Design */
        [data-testid="stSidebar"] { background-color: #003366; color: white; }
        [data-testid="stSidebar"] * { color: white !important; }
        
        /* Cards für Wettbewerbe */
        .comp-card {
            background-color: white !important;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            margin-bottom: 25px;
            border-left: 8px solid #003366;
            color: #31333F;
        }

        /* Verhindert, dass Streamlit-Inhalte die Card überlagern */
        .comp-card h3 {
            margin-top: 0 !important;
            margin-bottom: 15px !important;
        }
        
        /* Streamlit Elemente anpassen */
        .stButton>button {
            background-color: #003366;
            color: white;
            border-radius: 4px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNKTIONEN ---
def time_to_seconds(t_str):
    try:
        if not t_str or str(t_str).strip() in ["", "0", "00:00:00", "None", "nan"]: return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
        return 0
    except: return 0

# --- RENDER LOGIK ---
def render_competition(df, comp_name):
    df.columns = [str(c).strip() for c in df.columns]
    
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), "Bib")
    name_col = next((c for c in df.columns if any(k in c.lower() for k in ['name', 'nachname', 'vorname'])), "Name")
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)

    time_keywords = ['start', 'km', 'split', 'mess', 'zwischen']
    ordered_times = [c for c in df.columns if any(k in c.lower() for k in time_keywords) and c != goal_col] + [goal_col]

    if start_col and goal_col:
        for col in ordered_times: df[f'{col}_sec'] = df[col].apply(time_to_seconds)
        
        df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy() if status_col else df.copy()
        auf_strecke = df_reg[(df_reg[f'{start_col}_sec'] > 0) & (df_reg[f'{goal_col}_sec'] == 0)].copy()
        im_ziel = df_reg[df_reg[f'{goal_col}_sec'] > 0].copy()

        # REFERENZ-ZEIT Logik
        if not im_ziel.empty:
            now_sec = im_ziel[f'{goal_col}_sec'].max()
        else:
            now = datetime.now()
            now_sec = now.hour * 3600 + now.minute * 60 + now.second

        # Card-Container Start (HTML)
        # Wir rendern die Überschrift direkt in den Container
        st.markdown(f'''
            <div class="comp-card">
                <h3>🏆 {comp_name}</h3>
        ''', unsafe_allow_html=True)

        # Fortschrittsbalken Logik
        total_started = len(auf_strecke) + len(im_ziel)
        if total_started > 0:
            progress_val = len(im_ziel) / total_started
            st.write(f"**Gesamtfortschritt: {len(im_ziel)} von {total_started} Teilnehmern im Ziel**")
            st.progress(progress_val)
        
        st.markdown("<br>", unsafe_allow_html=True)

        if not auf_strecke.empty:
            # Sektor-Averages
            sector_averages = {}
            for i in range(len(ordered_times) - 1):
                col_a, col_b = ordered_times[i], ordered_times[i+1]
                fin = df_reg[(df_reg[f'{col_a}_sec'] > 0) & (df_reg[f'{col_b}_sec'] > 0)]
                if not fin.empty: sector_averages[col_a] = (fin[f'{col_b}_sec'] - fin[f'{col_a}_sec']).mean()

            def analyze_safety(row):
                last_point, last_sec = start_col, row[f'{start_col}_sec']
                for col_name in ordered_times:
                    if col_name != goal_col and row[f'{col_name}_sec'] > 0:
                        if row[f'{col_name}_sec'] >= last_sec:
                            last_point, last_sec = col_name, row[f'{col_name}_sec']
                
                diff_min = max(0, now_sec - last_sec) / 60
                avg_min = sector_averages.get(last_point, 3600) / 60
                is_overdue = diff_min > (avg_min * 1.5)
                
                status_label = f"{int(diff_min)}m (Schnitt: {int(avg_min)}m)"
                if is_overdue: status_label = "🚩 OVERDUE: " + status_label
                
                return pd.Series({'Letzter Kontakt': last_point, 'Sicherheits-Status': status_label, 'Sort_Min': diff_min})

            res = auf_strecke.apply(analyze_safety, axis=1)
            auf_strecke = pd.concat([auf_strecke, res], axis=1)
            
            st.info(f"Aktuell {len(auf_strecke)} Teilnehmer auf der Strecke (Referenzzeit: {timedelta(seconds=int(now_sec))})")
            
            disp = [c for c in [bib_col, name_col, 'Letzter Kontakt', 'Sicherheits-Status'] if c in auf_strecke.columns]
            st.dataframe(auf_strecke.sort_values('Sort_Min', ascending=False)[disp], use_container_width=True, hide_index=True)
        else:
            st.success("Alle Teilnehmer im Ziel.")
        
        st.markdown('</div>', unsafe_allow_html=True) # Card-Container Ende

# --- NAVIGATION ---
st.set_page_config(page_title="Race Monitor Pro", layout="wide")
apply_custom_design()

all_events = load_events()
public_event_name = st.query_params.get("event")

if public_event_name:
    st.title(f"Live Monitor: {public_event_name}")
    ev = next((e for e in all_events if e['name'] == public_event_name), None)
    if ev:
        try:
            res = requests.get(ev['url'], timeout=10).json()
            if isinstance(res, dict) and 'data' in res:
                df = pd.DataFrame(res['data'], columns=res.get('columns', []))
            else:
                df = pd.DataFrame(res)
            
            comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)
            if comp_col:
                for c in df[comp_col].unique(): render_competition(df[df[comp_col] == c], str(c))
            else: render_competition(df, ev['name'])
            time.sleep(30); st.rerun()
        except Exception as e: st.error(f"Fehler: {e}")
else:
    mode = st.sidebar.radio("Navigation", ["📊 Dashboard", "⚙️ API Verwaltung"])
    if mode == "⚙️ API Verwaltung":
        st.title("Event Setup")
        with st.form("new_ev"):
            n, u = st.text_input("Event Name"), st.text_input("RaceResult URL")
            if st.form_submit_button("Hinzufügen"):
                all_events.append({"name": n, "url": u}); save_events(all_events); st.rerun()
        for i, ev in enumerate(all_events):
            c1, c2 = st.columns([4, 1])
            c1.info(f"**{ev['name']}**")
            c1.code(f"/?event={urllib.parse.quote(ev['name'])}")
            if c2.button("Löschen", key=i): all_events.pop(i); save_events(all_events); st.rerun()
    elif mode == "📊 Dashboard":
        if not all_events: st.info("Bitte Event anlegen.")
        else:
            sel = st.selectbox("Event wählen", [e['name'] for e in all_events])
            ev = next(e for e in all_events if e['name'] == sel)
            try:
                res = requests.get(ev['url'], timeout=10).json()
                if isinstance(res, dict) and 'data' in res:
                    df = pd.DataFrame(res['data'], columns=res.get('columns', []))
                else:
                    df = pd.DataFrame(res)
                
                comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)
                if comp_col:
                    for c in df[comp_col].unique():
                        render_competition(df[df[comp_col] == c], str(c))
                else:
                    render_competition(df, ev['name'])
                
                time.sleep(30); st.rerun()
            except Exception as e: st.error(f"Fehler beim Laden: {e}")