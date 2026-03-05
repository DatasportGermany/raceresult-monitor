import streamlit as st
import pandas as pd
import requests
import time

# --- SEITEN-KONFIGURATION ---
st.set_page_config(page_title="Race Monitor Pro", layout="wide")

# --- URL PARAMETER LOGIK (Public Mode) ---
# Prüfen, ob ein Event-Name in der URL übergeben wurde (z.B. ?event=Trollinger)
query_params = st.query_params
public_event = query_params.get("event")

# --- HELPER FUNKTIONEN ---
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
        df_reg = df[df[status_col].astype(str).str.strip() == "0"].copy()

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

# --- EVENT SPEICHER (In einer echten App wäre hier eine DB besser) ---
if 'event_store' not in st.session_state:
    # Beispiel-Daten zur Demonstration (hier deine echten URLs eintragen oder über Admin-Mode zufügen)
    st.session_state.event_store = []

# --- NAVIGATION & VIEW LOGIK ---
if public_event:
    # PUBLIC MODE: Nur das Dashboard anzeigen, keine Sidebar
    st.title(f"📊 Live-Monitor: {public_event}")
    selected_event = next((e for e in st.session_state.event_store if e['name'] == public_event), None)
    
    if selected_event:
        try:
            res = requests.get(selected_event['url'], timeout=10)
            df = pd.DataFrame(res.json()['data'], columns=res.json().get('columns', []))
            comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz']), None)
            if comp_col:
                for comp in df[comp_col].unique(): render_competition(df[df[comp_col] == comp], str(comp))
            else: render_competition(df, public_event)
            time.sleep(30)
            st.rerun()
        except: st.error("Event-Daten konnten nicht geladen werden.")
    else:
        st.error("Dieses Event wurde nicht gefunden oder der Link ist abgelaufen.")
        if st.button("Zur Hauptseite"): st.query_params.clear()

else:
    # ADMIN MODE: Volle Funktionalität
    mode = st.sidebar.radio("Navigation", ["📊 Dashboard", "⚙️ API Verwaltung"])

    if mode == "⚙️ API Verwaltung":
        st.title("⚙️ API Verwaltung")
        with st.form("new_event"):
            n = st.text_input("Name")
            u = st.text_input("URL")
            if st.form_submit_button("Hinzufügen") and n and u:
                st.session_state.event_store.append({"name": n, "url": u})
                st.rerun()

        for i, ev in enumerate(st.session_state.event_store):
            col1, col2 = st.columns([4, 1])
            # SHARE LINK GENERIEREN
            base_url = "https://deine-app.streamlit.app" # Ersetze dies durch deine echte URL
            share_url = f"{base_url}/?event={ev['name'].replace(' ', '%20')}"
            col1.write(f"**{ev['name']}**")
            col1.code(share_url, language="text") # Zeigt den Link zum Kopieren an
            if col2.button("Löschen", key=i):
                st.session_state.event_store.pop(i)
                st.rerun()

    elif mode == "📊 Dashboard":
        st.title("📊 Monitor Dashboard")
        if not st.session_state.event_store:
            st.info("Keine Events konfiguriert.")
        else:
            sel_name = st.selectbox("Event wählen", [e['name'] for e in st.session_state.event_store])
            sel_ev = next(e for e in st.session_state.event_store if e['name'] == sel_name)
            # Hier folgt die normale render_competition Logik wie oben...
            # (Aus Platzgründen gekürzt, Logik bleibt identisch)
        
        # Hol die URL zum ausgewählten Namen
        selected_url = next(e['url'] for e in st.session_state.event_store if e['name'] == selected_event_name)
        
        refresh_rate = st.sidebar.slider("Auto-Refresh (Sekunden)", 10, 300, 30)
        
        # Daten laden und anzeigen
        try:
            res = requests.get(selected_url, timeout=10)
            json_data = res.json()
            if isinstance(json_data, dict) and 'data' in json_data:
                df = pd.DataFrame(json_data['data'], columns=json_data.get('columns', []))
            else:
                df = pd.DataFrame(json_data)
            
            # Wettbewerbs-Trennung
            comp_col = next((c for c in df.columns if c.lower() in ['wettbewerb', 'event', 'konkurrenz']), None)
            
            if comp_col:
                for comp in df[comp_col].unique():
                    render_competition(df[df[comp_col] == comp], str(comp))
            else:
                render_competition(df, selected_event_name)
                
            # Auto-Refresh
            time.sleep(refresh_rate)
            st.rerun()
            
        except Exception as e:
            st.error(f"Fehler beim Laden des Events: {e}")