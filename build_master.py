import pandas as pd
import numpy as np
import os
import re
import unicodedata
from scout_engine import ScoutEngine

BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna', 'Como']

def normalize_str(s):
    if pd.isna(s): return ""
    s = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return " ".join(s.split())

def trova_miglior_match_stats(nome_cercato, ruolo_cercato, df_stats):
    if df_stats.empty: return None
    
    tokens_cercato = set(normalize_str(nome_cercato).split())
    if not tokens_cercato: return None
    
    matches = []
    for idx, row in df_stats.iterrows():
        tokens_row = set(str(row.get('Nome_Norm', '')).split())
        if not tokens_row: continue
        
        if tokens_cercato == tokens_row or tokens_cercato.issubset(tokens_row) or tokens_row.issubset(tokens_cercato):
            matches.append(row)
            
    if not matches:
        cognomi = [w for w in tokens_cercato if len(w) >= 4]
        for cog in cognomi:
            sub_df = df_stats[df_stats['Nome_Norm'].str.contains(cog, na=False, regex=False)]
            for _, row in sub_df.iterrows():
                matches.append(row)
                
    if not matches: return None
        
    df_matches = pd.DataFrame(matches).drop_duplicates()
    
    if 'R' in df_matches.columns:
        same_role = df_matches[df_matches['R'].astype(str).str.upper() == ruolo_cercato.upper()]
        if not same_role.empty: df_matches = same_role

    if 'Pv' in df_matches.columns:
        df_matches['Pv_Num'] = pd.to_numeric(df_matches['Pv'], errors='coerce').fillna(0)
        df_matches = df_matches.sort_values(by='Pv_Num', ascending=False)
        
    return df_matches.iloc[0]

def main():
    print("🚀 Avvio Master Engine - AUTO-SYNC LIVE ROSE & MASTER INDIPENDENTE...")
    scout = ScoutEngine()

    # 1. CARICAMENTO STATISTICHE HISTORIC
    excel_file = "Quotazioni_Fantacalcio_Stagione_2025_26.xlsx"
    df_stats = pd.DataFrame()
    if os.path.exists(excel_file):
        try:
            df_stats = pd.read_excel(excel_file, header=1)
            df_stats['Nome_Norm'] = df_stats['Nome'].apply(normalize_str)
            print("✅ Storico Excel caricato.")
        except Exception as e:
            print(f"⚠️ Errore Excel: {e}")

    # 2. CARICAMENTO LISTONE BASE LOCALE
    csv_file = "Lista-FantaAsta-Fantacalcio.csv"
    if not os.path.exists(csv_file):
        print(f"❌ File base {csv_file} mancante.")
        return

    with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
        first_line = f.readline()
    sep = ';' if ';' in first_line else ','

    df_listone = pd.read_csv(csv_file, sep=sep, header=None, dtype=str, on_bad_lines='skip')
    if len(df_listone.columns) > 19: df_listone = df_listone.iloc[:, :19]
    while len(df_listone.columns) < 19: df_listone[len(df_listone.columns)] = ""

    df_listone.columns = [
        'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
        'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
        'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
    ]

    df_listone['R'] = df_listone['R'].astype(str).str.strip().str.upper()
    df_listone = df_listone[df_listone['R'].isin(['P', 'D', 'C', 'A'])]

    # -------------------------------------------------------------
    # 3. LIVE SCANNER API-FOOTBALL (Sincronizzazione Rose Serie A)
    # -------------------------------------------------------------
    print("🌐 Sincronizzazione rose ufficiali Serie A via API-Football...")
    try:
        # Interroga lo ScoutEngine per scaricare i nuovi trasferimenti ufficiali
        nuovi_giocatori_api = scout.sincronizza_rose_serie_a() 
        if nuovi_giocatori_api:
            for g_api in nuovi_giocatori_api:
                norm_api_nome = normalize_str(g_api['nome'])
                
                # Controlla se il giocatore esiste già nel listone base
                idx_match = df_listone[df_listone['Nome'].apply(normalize_str) == norm_api_nome].index
                if not idx_match.empty:
                    # AGGIORNA LA SQUADRA (es. Spence spostato all'Inter)
                    df_listone.loc[idx_match, 'Squadra'] = g_api['squadra']
                    print(f"🔄 TRASFERIMENTO RILEVATO: {g_api['nome']} -> {g_api['squadra']}")
                else:
                    # NUOVO ACQUISTO NON PRESENTE NEL LISTONE UFFICIALE -> CREA SCHEDA NUOVA
                    nuova_riga = {
                        'Id': str(9000 + len(df_listone)),
                        'Nome_Breve': g_api['nome'],
                        'Nome': g_api['nome'],
                        'R': g_api['ruolo'],
                        'Ruolo_Esteso': g_api['ruolo'],
                        'Qt.A': str(g_api.get('quotazione_base', 10)),
                        'Qt.I': str(g_api.get('quotazione_base', 10)),
                        'Squadra': g_api['squadra'],
                        'FVM': '1.0'
                    }
                    df_listone = pd.concat([df_listone, pd.DataFrame([nuova_riga])], ignore_index=True)
                    print(f"🆕 NUOVO GIOCATORE INSERITO DA API: {g_api['nome']} ({g_api['squadra']})")
    except Exception as e:
        print(f"⚠️ Sincronizzazione API completata con avvisi: {e}")

    # -------------------------------------------------------------
    # 4. CALCOLO FANTAMEDIA E FVM FINALE
    # -------------------------------------------------------------
    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row['Nome']).strip()
        ruolo = str(row['R']).strip()
        squadra = str(row['Squadra']).strip()

        try: qt_i = float(str(row['Qt.I']).replace(',', '.'))
        except: qt_i = 1.0
        try: qt_a = float(str(row['Qt.A']).replace(',', '.'))
        except: qt_a = qt_i
        best_qt = max(qt_i, qt_a)

        fm_val = None

        # A) Ricerca nello storico
        best_match = trova_miglior_match_stats(nome, ruolo, df_stats)
        if best_match is not None:
            try: fm_val = float(str(best_match.get('Fm', '')).replace(',', '.'))
            except: pass

        # B) Se manca lo storico (Nuovo Arrivo/API), interroga l'IA
        if fm_val is None or fm_val <= 0:
            try: fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
            except: fm_val = None
            if fm_val is None: fm_val = 5.8

        # C) Algoritmo FVM con curve di potenza
        if ruolo == 'A':
            if best_qt >= 25: base_fvm = (best_qt * 8.5) + (max(0, fm_val - 5.5) ** 2) * 30
            elif best_qt >= 10: base_fvm = (best_qt * 4.5) + (max(0, fm_val - 5.5) ** 2) * 15
            else: base_fvm = max(best_qt * 3.0, 12.0 if squadra in BIG_TEAMS else 4.0)
        elif ruolo == 'C':
            if best_qt >= 18: base_fvm = (best_qt * 6.0) + (max(0, fm_val - 5.5) ** 2) * 20
            elif best_qt >= 8: base_fvm = (best_qt * 3.5) + (max(0, fm_val - 5.5) ** 2) * 12
            else: base_fvm = max(best_qt * 2.5, 8.0 if squadra in BIG_TEAMS else 3.0)
        elif ruolo == 'D': base_fvm = best_qt * 2.2 + max(0, (fm_val - 5.5) * 12)
        elif ruolo == 'P': base_fvm = best_qt * 2.5 + max(0, (fm_val - 5.0) * 15)
        else: base_fvm = best_qt * 1.5

        if squadra in BIG_TEAMS and best_qt >= 5.0: base_fvm *= 1.12

        fvm_finale = round(min(500.0, max(1.0, float(base_fvm))), 1)
        fvm_calcolati.append(fvm_finale)

    df_listone['FVM'] = fvm_calcolati
    df_listone = df_listone.fillna("")
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv RIGENERATA CON SUCCESSO!")

if __name__ == '__main__':
    main()
