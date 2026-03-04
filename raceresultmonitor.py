def render_competition(df, comp_name):
    """Prüft: Startzeit da, Zielzeit wirklich leer?"""
    df.columns = [str(c).strip() for c in df.columns]
    
    # 1. Spalten identifizieren
    bib_col = next((c for c in df.columns if 'bib' in c.lower() or 'stnr' in c.lower()), "Bib")
    name_col = next((c for c in df.columns if 'name' in c.lower()), "Name")
    start_col = next((c for c in df.columns if 'start' in c.lower()), None)
    goal_col = next((c for c in df.columns if 'ziel' in c.lower() or 'finish' in c.lower()), None)
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)

    if start_col and goal_col:
        # Konvertierung zu Sekunden (0 wenn leer/ungültig)
        df['S_Sec'] = df[start_col].apply(time_to_seconds)
        df['G_Sec'] = df[goal_col].apply(time_to_seconds)

        # WICHTIG: Wer DNF/DSQ ist, zählt nicht als "auf der Strecke"
        # Wir filtern hier NUR Teilnehmer, die den Status "0" haben
        if status_col:
            df_regulär = df[df[status_col].astype(str).str.strip() == "0"].copy()
        else:
            df_regulär = df.copy()

        # LOGIK: 
        # Auf der Strecke = Startzeit > 0 UND Zielzeit ist (0 ODER leer ODER None)
        auf_strecke = df_regulär[
            (df_regulär['S_Sec'] > 0) & 
            ((df_regulär['G_Sec'] == 0) | (df_regulär[goal_col].isna()) | (df_regulär[goal_col].astype(str).str.strip() == ""))
        ]
        
        im_ziel = df_regulär[df_regulär['G_Sec'] > 0]
        
        with st.expander(f"🏆 {comp_name}", expanded=True):
            if not auf_strecke.empty:
                st.warning(f"🔔 {len(auf_strecke)} Teilnehmer noch auf der Strecke")
                
                # Fortschrittsbalken
                total_started = len(im_ziel) + len(auf_strecke)
                progress = len(im_ziel) / total_started if total_started > 0 else 0
                st.progress(progress)
                
                # Tabelle anzeigen
                disp = [c for c in [bib_col, name_col, start_col] if c in df_regulär.columns]
                st.dataframe(auf_strecke[disp], use_container_width=True, hide_index=True)
            else:
                if not im_ziel.empty:
                    st.success(f"✅ Alle {len(im_ziel)} Teilnehmer sind im Ziel.")
                else:
                    st.info("Keine gestarteten Teilnehmer gefunden.")
    else:
        st.error(f"Spalten fehlen in {comp_name}. Vorhanden: {list(df.columns)}")
