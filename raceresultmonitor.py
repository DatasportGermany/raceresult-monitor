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

# --- DESIGN (ADAPTIV) ---
def apply_custom_design():
    st.markdown("""
        <style>
        .comp-container {
            border: 1px solid #464b5d;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 25px;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid #464b5d;
        }
        </style>
    """, unsafe_allow_html=True)

def time_to_seconds(t_str):
    try:
        if not t_str or str(t_str).strip() in ["", "0", "00:00:00", "None", "nan"]: return 0
        parts = str(t_str).split(':')
        if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
        return 0
    except: return 0

def fetch_race_data(url):
    sep = "&" if "?" in url else "?"
    clean_url = f"{url}{sep}nocache={int(time.time())}"
    r = requests.get(clean_url, timeout=10).json()
    return r

# --- RENDER LOGIK ---
def render_competition(df, comp_name, time_mode):
    df.columns = [str(c).strip() for c in df.columns]
    
    # Robuste Spaltensuche
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr', 'snr', 'nr']), "Bib")
    name_col = next((c for c in df.columns if any(k in c.lower() for k in ['name', 'nachname', 'vorname', 'teilnehmer'])), None)
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

        # ZEIT-LOGIK (UTC+1 Fix)
        now_local = datetime.utcnow() + timedelta(hours=1) 
        
        if time_mode == "Simulation (Letzter Finisher)" and not im_ziel.empty:
            now_sec = im_ziel[f'{goal_col}_sec'].max()
            label = "Simuliert"
        else:
            now_sec = now_local.hour * 3600 + now_local.minute * 60 + now_local.second
            label = "Echtzeit"

        # --- AB HIER: REINES STREAMLIT DESIGN OHNE HTML-DIVS ---
        st.subheader(f"🏆 {comp_name}")

        total_gestartet = len(auf_strecke) + len(im_ziel)
        
        if total_gestartet == 0:
            st.info("Noch nicht gestartet")
        elif not auf_strecke.empty:
            noch_fehlend = len(auf_strecke)
            progress_val = len(im_ziel) / total_gestartet
            st.write(f"Fortschritt: {len(im_ziel)} von {total_gestartet} im Ziel ({noch_fehlend} fehlen noch)")
            st.progress(progress_val)

            # Sicherheits-Analyse
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
                return pd.Series({
                    'Letzter Kontakt': lp, 
                    'Sicherheits-Status': status, 
                    'Sort_Min': diff_m,
                    'Is_Overdue': 1 if is_overdue else 0
                })

            res = auf_strecke.apply(analyze_safety, axis=1)
            auf_strecke = pd.concat([auf_strecke, res], axis=1)
            
            # Startnummer linksbündig & Sortierung
            auf_strecke[bib_col] = auf_strecke[bib_col].astype(str)
            auf_strecke_sorted = auf_strecke.sort_values(by=['Is_Overdue', 'Sort_Min'], ascending=[False, False])
            
            st.info(f"Basis-Zeit {label}: {str(timedelta(seconds=int(now_sec)))} — Update: {now_local.strftime('%H:%M:%S')}")
            
            disp_cols = [bib_col]
            if name_col: disp_cols.append(name_col)
            disp_cols += ['Letzter Kontakt', 'Sicherheits-Status']
            
            st.dataframe(auf_strecke_sorted[disp_cols], use_container_width=True, hide_index=True)
            st.divider() # Trennlinie statt weißem Kasten
        else:
            st.success("Alle Teilnehmer im Ziel.")
            st.divider()

# --- APP FLOW ---
st.set_page_config(page_title="Race Monitor Pro", layout="wide")
apply_custom_design()
all_events = load_events()

st.sidebar.title("Einstellungen")
t_mode = st.sidebar.radio("Zeit-Referenz", ["Live-Uhrzeit (System)", "Simulation (Letzter Finisher)"])
sync_interval = st.sidebar.slider("Synchronisations-Intervall (s)", 5, 300, 10)

p_event = st.query_params.get("event")

if p_event:
    st.title(f"Live Monitor: {p_event}")
    ev = next((e for e in all_events if e['name'] == p_event), None)
    if ev:
        try:
            r = fetch_race_data(ev['url'])
            df = pd.DataFrame(r['data'], columns=r.get('columns', [])) if 'data' in r else pd.DataFrame(r)
            df.columns = [str(c).strip() for c in df.columns]
            c_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)
            if c_col:
                for c in df[c_col].unique(): render_competition(df[df[c_col] == c], str(c), t_mode)
            else: render_competition(df, ev['name'], t_mode)
            time.sleep(sync_interval)
            st.rerun()
        except: st.error("Ladefehler.")
else:
    mode = st.sidebar.radio("Navigation", ["📊 Dashboard", "⚙️ API Verwaltung"])
    if mode == "⚙️ API Verwaltung":
        st.title("Event Setup")
        with st.form("new_ev"):
            n, u = st.text_input("Name"), st.text_input("URL der RR API")
            if st.form_submit_button("Hinzufügen"):
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
                r = fetch_race_data(ev['url'])
                df = pd.DataFrame(r['data'], columns=r.get('columns', [])) if 'data' in r else pd.DataFrame(r)
                df.columns = [str(c).strip() for c in df.columns]
                c_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz', 'competition']), None)
                if c_col:
                    for c_val in df[c_col].unique(): 
                        render_competition(df[df[c_col] == c_val], str(c_val), t_mode)
                else: 
                    render_competition(df, ev['name'], t_mode)
                time.sleep(sync_interval)
                st.rerun()
            except Exception as e: st.error(f"Ladefehler: {e}")