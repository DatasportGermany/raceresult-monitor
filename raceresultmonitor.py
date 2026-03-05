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
        .main { background-color: #f4f7f9; }
        h1, h2, h3 { color: #003366; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-weight: 700; }
        
        /* Sidebar Design */
        [data-testid="stSidebar"] { background-color: #003366; color: white; }
        [data-testid="stSidebar"] * { color: white !important; }
        
        /* Cards für Wettbewerbe */
        .comp-card {
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            margin-bottom: 25px;
            border-left: 5px solid #003366;
        }
        
        /* Badge-System für Status */
        .status-badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: bold;
        }
        .overdue { background-color: #ffebee; color: #c62828; border: 1px solid #c62828; }
        .normal { background-color: #e3f2fd; color: #1565c0; border: 1px solid #1565c0; }
        
        /* Streamlit Elemente anpassen */
        .stButton>button {
            background-color: #003366;
            color: white;
            border-radius: 4px;
            border: none;
            padding: 0.5rem 1rem;
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
        # Zeit-Spalten konvertieren
        for col in ordered_times: df[f'{col}_sec'] = df[col].apply(time_to_seconds)
        
        df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy() if status_col else df.copy()
        auf_strecke = df_reg[(df_reg[f'{start_col}_sec'] > 0) & (df_reg[f'{goal_col}_sec'] == 0)].copy()
        im_ziel = df_reg[df_reg[f'{goal_col}_sec'] > 0].copy()

        # REFERENZ-ZEIT Logik (Fix für alte Events)
        if not im_ziel.empty:
            now_sec = im_ziel[f'{goal_col}_sec'].max()
        else:
            now = datetime.now()
            now_sec = now.hour * 3600 + now.minute * 60 + now.second

        # Card-Container Start
        st.markdown(f'<div class="comp-card">', unsafe_allow_html=True)
        st.subheader(f"🏆 {comp_name}")

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
            df = pd.DataFrame(res['data'], columns=res.get('columns', [])) if 'data' in res else pd.DataFrame(res)
            comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz']), None)
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
        if not all_events: 
            st.info("Bitte zuerst unter 'API Verwaltung' ein Event anlegen.")
        else:
            sel_name = st.selectbox("Event wählen", [e['name'] for e in all_events])
            selected_ev = next(e for e in all_events if e['name'] == sel_name)
            
            try:
                # API Daten abrufen
                response = requests.get(selected_ev['url'], timeout=10)
                res_json = response.json()
                
                # DataFrame erstellen (robust gegen verschiedene Formate)
                if isinstance(res_json, dict) and 'data' in res_json:
                    df = pd.DataFrame(res_json['data'], columns=res_json.get('columns', []))
                else:
                    df = pd.DataFrame(res_json)
                
                # Spaltennamen säubern
                df.columns = [str(c).strip() for c in df.columns]
                
                # Suchen nach der Wettbewerbs-Spalte
                comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)
                
                if comp_col:
                    # Wenn mehrere Wettbewerbe in einer API sind
                    for comp in df[comp_col].unique():
                        render_competition(df[df[comp_col] == comp], str(comp))
                        st.divider()
                else:
                    # Wenn nur ein Wettbewerb in der API ist
                    render_competition(df, selected_ev['name'])
                    
                # Auto-Refresh Logik im Dashboard
                refresh_rate = st.sidebar.slider("Auto-Refresh (s)", 10, 300, 30)
                time.sleep(refresh_rate)
                st.rerun()
                
            except Exception as e:
                st.error(f"Fehler beim Laden der API: {e}")
                st.info("Hinweis: Überprüfe, ob die URL korrekt ist und die API Daten im JSON-Format liefert.")