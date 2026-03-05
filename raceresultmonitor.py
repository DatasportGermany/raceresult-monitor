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
    df.columns = [str(c).strip() for c in df.columns]
    
    bib_col = next((c for c in df.columns if c.lower() in ['startnummer', 'bib', 'stnr']), "Startnummer")
    name_col = next((c for c in df.columns if 'name' in c.lower()), "Name")
    start_col = next((c for c in df.columns if c.lower() == 'start' or 'startzeit' in c.lower()), None)
    goal_col = next((c for c in df.columns if c.lower() == 'ziel' or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), "Status")

    if start_col and goal_col:
        df['S_Sec'] = df[start_col].apply(time_to_seconds)
        df['G_Sec'] = df[goal_col].apply(time_to_seconds)
        
        # Status Filter
        if status_col in df.columns:
            df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy()
        else:
            df_reg = df.copy()

        auf_strecke = df_reg[(df_reg['S_Sec'] > 0) & (df_reg[goal_col].apply(is_empty))].copy()
        im_ziel = df_reg[(df_reg['S_Sec'] > 0) & (~df_reg[goal_col].apply(is_empty))].copy()
        
        st.subheader(f"🏆 {comp_name}")
        
        col_stats, col_graph = st.columns([1, 1])

        with col_stats:
            if not auf_strecke.empty:
                st.warning(f"🔔 {len(auf_strecke)} Teilnehmer auf der Strecke")
                total = len(im_ziel) + len(auf_strecke)
                st.progress(len(im_ziel) / total)
                
                disp = [c for c in [bib_col, name_col, start_col] if c in df_reg.columns]
                st.dataframe(auf_strecke[disp], use_container_width=True, hide_index=True, height=300)
            else:
                st.success("✅ Alle Teilnehmer im Ziel.")

        with col_graph:
            # --- PROGNOSE LOGIK ---
            if not auf_strecke.empty and not im_ziel.empty:
                # Durchschnittliche Nettozeit der Finisher berechnen
                avg_netto = (im_ziel['G_Sec'] - im_ziel['S_Sec']).mean()
                
                # Erwartete Zielzeit für Läufer auf der Strecke (Start + Durchschnitt)
                auf_strecke['ETA_Sec'] = auf_strecke['S_Sec'] + avg_netto
                
                # In Uhrzeit-Intervalle gruppieren (alle 10 Min)
                def get_time_bin(s):
                    dt = datetime(2026, 1, 1) + timedelta(seconds=int(s))
                    # Runden auf 10 Minuten
                    discard = timedelta(minutes=dt.minute % 10, seconds=dt.second, microseconds=dt.microsecond)
                    dt -= discard
                    return dt.strftime("%H:%M")

                auf_strecke['ETA_Bin'] = auf_strecke['ETA_Sec'].apply(get_time_bin)
                eta_counts = auf_strecke.groupby('ETA_Bin').size().reset_index(name='Anzahl')

                # Plotly Chart
                fig = go.Figure(go.Bar(
                    x=eta_counts['ETA_Bin'],
                    y=eta_counts['Anzahl'],
                    marker_color='#1f77b4',
                    hovertemplate='Zeit: %{x}<br>Erwartet: %{y} Pers.<extra></extra>'
                ))
                fig.update_layout(
                    title="Ankunfts-Prognose (Wann kommen die Leute?)",
                    xaxis_title="Erwartete Uhrzeit",
                    yaxis_title="Anzahl Personen",
                    height=350,
                    margin=dict(t=40, b=0, l=0, r=0)
                )
                st.plotly_chart(fig, use_container_width=True)
            elif not auf_strecke.empty:
                st.info("Sammle erste Finisher-Daten für die Prognose...")

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