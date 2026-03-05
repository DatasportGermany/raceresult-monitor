import streamlit as st
import pandas as pd
import requests
import time
import urllib.parse
import json
import os
from datetime import datetime, timedelta

# --- DATENBANK ---
DB_FILE = "event_db.json"

def load_events():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return []
    return []

def save_events(events):
    with open(DB_FILE, "w") as f: json.dump(events, f)

# --- DATASPORT DESIGN SYSTEM ---
def apply_custom_design():
    st.markdown("""
        <style>
        /* Globaler Hintergrund */
        .stApp { background-color: #f4f7f9 !important; }
        
        /* Sidebar (Datasport Dunkelblau) */
        [data-testid="stSidebar"] { background-color: #003366 !important; }
        [data-testid="stSidebar"] * { color: white !important; }
        
        /* Die weiße Card-Hülle */
        .comp-card {
            background-color: #ffffff !important;
            padding: 25px;
            border-radius: 4px;
            border-left: 6px solid #003366;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            color: #31333F !important; /* Zwingt Schrift auf Dunkelgrau */
        }
        
        /* Titel innerhalb der Card */
        .comp-card h3 {
            color: #003366 !important;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-size: 1.5rem !important;
            margin-bottom: 20px !important;
            margin-top: 0 !important;
            font-weight: 700 !important;
        }

        /* Info-Box für Referenzzeit */
        .status-info {
            background-color: #eef2f7 !important;
            color: #445566 !important;
            padding: 10px 15px;
            border-radius: 4px;
            font-size: 0.95rem;
            margin-bottom: 20px;
            border-left: 3px solid #003366;
            font-weight: 500;
        }
        
        /* Anpassung für Dataframes innerhalb der Card */
        [data-testid="stTable"], [data-testid="stDataFrame"] {
            background-color: white !important;
            color: black !important;
        }
        </style>
    """, unsafe_allow_html=True)

# --- HELPER ---
def time_to_seconds(t_str):
    try:
        if not t_str or str(t_str).strip() in ["", "0", "00:00:00", "None", "nan"]: return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
        return 0
    except: return 0

# --- KERNLOGIK ---
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
        im_ziel = df_reg[df_reg[f'{goal_col}_sec'] > 0].copy()
        auf_strecke = df_reg[(df_reg[f'{start_col}_sec'] > 0) & (df_reg[f'{goal_col}_sec'] == 0)].copy()

        # Zeit-Referenz (Letzter Finisher oder Jetzt)
        if not im_ziel.empty:
            now_sec = im_ziel[f'{goal_col}_sec'].max()
        else:
            n = datetime.now()
            now_sec = n.hour * 3600 + n.minute * 60 + n.second

        # Card-Container START
        st.markdown(f'<div class="comp-card"><h3>🏆 {comp_name}</h3>', unsafe_allow_html=True)

        if not auf_strecke.empty:
            # Sektor-Averages
            sector_averages = {}
            for i in range(len(ordered_times) - 1):
                col_a, col_b = ordered_times[i], ordered_times[i+1]
                fin = df_reg[(df_reg[f'{col_a}_sec'] > 0) & (df_reg[f'{col_b}_sec'] > 0)]
                if not fin.empty: sector_averages[col_a] = (fin[f'{col_b}_sec'] - fin[f'{col_a}_sec']).mean()

            def analyze_safety(row):
                lp, ls = start_col, row[f'{start_col}_sec']
                for c in ordered_times:
                    if c != goal_col and row[f'{c}_sec'] > 0:
                        if row[f'{c}_sec'] >= ls: lp, ls = c, row[f'{c}_sec']
                
                diff_m = max(0, now_sec - ls) / 60
                avg_m = sector_averages.get(lp, 3600) / 60
                is_overdue = diff_m > (avg_m * 1.5)
                
                status = f"{int(diff_m)}m (Schnitt: {int(avg_m)}m)"
                if is_overdue: status = "🚩 OVERDUE: " + status
                return pd.Series({'Letzter Kontakt': lp, 'Sicherheits-Status': status, 'Sort_Min': diff_m})

            safety_res = auf_strecke.apply(analyze_safety, axis=1)
            auf_strecke = pd.concat([auf_strecke, safety_res], axis=1)
            
            ref_str = str(timedelta(seconds=int(now_sec)))
            st.markdown(f'<div class="status-info">Aktuell {len(auf_strecke)} Teilnehmer unterwegs (Ref-Zeit: {ref_str})</div>', unsafe_allow_html=True)
            
            disp = [c for c in [bib_col, name_col, 'Letzter Kontakt', 'Sicherheits-Status'] if c in auf_strecke.columns]
            st.dataframe(auf_strecke.sort_values('Sort_Min', ascending=False)[disp], use_container_width=True, hide_index=True)
        else:
            st.markdown('<div class="status-info">✅ Alle Teilnehmer im Ziel.</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True) # Card-Container ENDE

# --- MAIN APP ---
apply_custom_design()
all_events = load_events()
p_event = st.query_params.get("event")

if p_event:
    st.title(f"Live Monitor: {p_event}")
    ev = next((e for e in all_events if e['name'] == p_event), None)
    if ev:
        try:
            r = requests.get(ev['url'], timeout=10).json()
            df = pd.DataFrame(r['data'], columns=r.get('columns', [])) if 'data' in r else pd.DataFrame(r)
            df.columns = [str(c).strip() for c in df.columns]
            c_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)
            if c_col:
                for c in df[c_col].unique(): render_competition(df[df[c_col] == c], str(c))
            else: render_competition(df, ev['name'])
            time.sleep(30); st.rerun()
        except: st.error("Ladefehler.")
else:
    mode = st.sidebar.radio("Navigation", ["📊 Dashboard", "⚙️ API Verwaltung"])
    
    if mode == "⚙️ API Verwaltung":
        st.title("Event Setup")
        with st.form("new_ev"):
            n, u = st.text_input("Name"), st.text_input("URL")
            if st.form_submit_button("Hinzufügen") and n and u:
                all_events.append({"name": n, "url": u}); save_events(all_events); st.rerun()
        for i, ev in enumerate(all_events):
            c1, c2 = st.columns([4, 1])
            c1.info(f"**{ev['name']}**")
            c1.code(f"/?event={urllib.parse.quote(ev['name'])}")
            if c2.button("Löschen", key=i): all_events.pop(i); save_events(all_events); st.rerun()
            
    elif mode == "📊 Dashboard":
        if not all_events: st.info("Keine Events konfiguriert.")
        else:
            sel = st.selectbox("Event wählen", [e['name'] for e in all_events])
            ev = next(e for e in all_events if e['name'] == sel)
            try:
                r = requests.get(ev['url'], timeout=10).json()
                df = pd.DataFrame(r['data'], columns=r.get('columns', [])) if 'data' in r else pd.DataFrame(r)
                df.columns = [str(c).strip() for c in df.columns]
                c_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)
                if c_col:
                    for c in df[c_col].unique(): render_competition(df[df[c_col] == c], str(c))
                else: render_competition(df, ev['name'])
                time.sleep(30); st.rerun()
            except: st.error("Fehler beim Laden.")