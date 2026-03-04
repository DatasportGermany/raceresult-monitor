def render_competition(df, comp_name):
    """Fokus: Wer fehlt noch?"""
    df.columns = [str(c).strip() for c in df.columns]
    
    # 1. Nur Teilnehmer mit Status 0 (regulär) betrachten
    status_col = next((c for c in df.columns if 'status' in c.lower()), None)
    if status_col:
        df = df[df[status_col].astype(str).str.strip() == "0"].copy()

    # 2. Relevante Spalten identifizieren
    bib_col = next((c for c in df.columns if 'bib' in c.lower() or 'stnr' in c.lower()), "Bib")
    name_col = next((c for c in df.columns if 'name' in c.lower()), "Name")
    start_col = next((c for c in df.columns if 'start' in c.lower()), None)
    goal_col = next((c for c in df.columns if 'ziel' in c.lower() or 'finish' in c.lower()), None)

    if start_col and goal_col:
        # Umwandlung für den Vergleich (Sekunden)
        df['S_Sec'] = df[start_col].apply(time_to_seconds)
        df['G_Sec'] = df[goal_col].apply(time_to_seconds)

        # DIE LOGIK: Start vorhanden (S_Sec > 0), Ziel fehlt (G_Sec == 0)
        auf_strecke = df[(df['S_Sec'] > 0) & (df['G_Sec'] == 0)]
        im_ziel = df[df['G_Sec'] > 0]
        
        with st.expander(f"🏆 {comp_name}", expanded=True):
            if not auf_strecke.empty:
                # Alarm-Anzeige: Gelbe Warnung mit der Anzahl der fehlenden Personen
                st.warning(f"🔔 {len(auf_strecke)} Teilnehmer aktuell auf der Strecke")
                
                # Fortschrittsbalken: Ziel / (Ziel + Strecke)
                total_active = len(im_ziel) + len(auf_strecke)
                progress_val = len(im_ziel) / total_active if total_active > 0 else 0
                st.progress(progress_val)
                
                # Liste der vermissten Personen
                st.markdown("**Liste der fehlenden Teilnehmer:**")
                st.dataframe(
                    auf_strecke[[bib_col, name_col, start_col]], 
                    use_container_width=True,
                    hide_index=True
                )
            else:
                # Wenn alle im Ziel sind (oder noch keiner gestartet ist)
                if not im_ziel.empty:
                    st.success(f"✅ Alle {len(im_ziel)} gestarteten Teilnehmer sind im Ziel.")
                else:
                    st.info("Warten auf den ersten Start...")
    else:
        st.error(f"Spaltenfehler: Konnte Start- oder Zielzeit in '{comp_name}' nicht finden.")
