import streamlit as st
import pandas as pd
import requests
import time
import urllib.parse
import json
import os

# --- DATEI-PFAD FÜR SPEICHERUNG ---
DB_FILE = "event_db.json"

# --- HELPER FÜR DATENBANK ---
def load_events():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return []

def save_events(events):
    with open(DB_FILE, "w") as f:
        json.dump(events, f)

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Race Monitor Pro", layout="wide")

# --- URL PARAMETER LOGIK ---
public_event_name = st.query_params.get("event")

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
    df.columns = [str(c).strip() for c in df.columns]
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), "Startnummer")
    name_col = next((c for c in df.columns if 'name' in c.lower()), "Name")
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), "Status")

    if start_col and goal_col:
        df['S_Sec'] = df[start_col].apply(time_to_seconds)
        df['G_Sec'] = df[goal_col].apply(time_to_seconds)
        
        if status_col in df.columns:
            df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy()
        else:
            df_reg = df.copy()

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
                if not im_ziel.empty: st.success(f"✅ Alle {len(im_ziel)} Teilnehmer im Ziel.")
                else: st.info("Warten auf Starts...")
    else:
        st.error(f"Spaltenfehler in '{comp_name}'.")

def run_dashboard(event_obj):
    refresh_rate = 30
    if not public_event_name:
        refresh_rate = st.sidebar.slider("Auto-Refresh (s)", 10, 300, 30)

    try:
        res = requests.get(event_obj['url'], timeout=10)
        data = res.json()
        df = pd.DataFrame(data['data'], columns=data.get('columns', []))
        comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz']), None)
        
        if comp_col:
            for comp in df[comp_col].unique():
                render_competition(df[df[comp_col] == comp], str(comp))
        else:
            render_competition(df, event_obj['name'])
            
        time.sleep(refresh_rate)
        st.rerun()
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")

# --- APP NAVIGATION ---
all_events = load_events()

if public_event_name:
    # --- PUBLIC MODE ---
    st.title(f"📊 Live-Monitor: {public_event_name}")
    selected_event = next((e for e in all_events if e['name'] == public_event_name), None)
    if selected_event:
        run_dashboard(selected_event)
    else:
        st.error(f"Event '{public_event_name}' nicht gefunden. Wurde es gelöscht?")
else:
    # --- ADMIN MODE ---
    mode = st.sidebar.radio("Navigation", ["📊 Dashboard", "⚙️ API Verwaltung"])

    if mode == "⚙️ API Verwaltung":
        st.title("⚙️ API Verwaltung")
        with st.form("new_event", clear_on_submit=True):
            n = st.text_input("Name des Events")
            u = st.text_input("RaceResult JSON URL")
            if st.form_submit_button("Hinzufügen") and n and u:
                all_events.append({"name": n, "url": u})
                save_events(all_events)
                st.success("Gespeichert!")
                st.rerun()

        st.subheader("Gespeicherte Events & Share-Links")
        for i, ev in enumerate(all_events):
            col1, col2 = st.columns([4, 1])
            encoded_name = urllib.parse.quote(ev['name'])
            share_url = f"/?event={encoded_name}" 
            col1.write(f"**{ev['name']}**")
            col1.code(share_url, language="text")
            if col2.button("Löschen", key=f"del_{i}"):
                all_events.pop(i)
                save_events(all_events)
                st.rerun()

    elif mode == "📊 Dashboard":
        st.title("📊 Monitor Dashboard")
        if not all_events:
            st.info("Bitte zuerst unter 'API Verwaltung' ein Event anlegen.")
        else:
            sel_name = st.selectbox("Wähle ein Event:", [e['name'] for e in all_events])
            selected_event = next(e for e in all_events if e['name'] == sel_name)
            run_dashboard(selected_event)