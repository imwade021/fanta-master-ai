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

def match_nomi_abbreviati(nome_lungo, nome_breve):
    n1 = normalize_str(nome_lungo).split()
    n2 = normalize_str(nome_breve).split()
    if not n1 or not n2: return False
    if n1[-1] == n2[-1] and n1[0][0] == n2[0][0]:
        return True
    return False

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
    print("🚀 Avvio Master Engine V11.0 - INIEZIONE STATISTICHE NEL CSV MASTER...")
    scout = ScoutEngine()

    excel_file = "Quotazioni_Fantacalcio_Stagione_2025_26.xlsx"
    df_stats = pd.DataFrame()
    if os.path.exists(excel_file):
        try:
            df_stats = pd.read_excel(excel_file, header=1)
            df_stats['Nome_Norm'] = df_stats['Nome'].apply(normalize_str)
            print("✅ Storico Excel caricato.")
        except Exception as e:
            print(f"⚠️ Errore Excel: {e}")

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

    print("🌐 Sincronizzazione API con DEDUPLICAZIONE...")
    try:
        nuovi_giocatori_api = scout.sincronizza_rose_serie_a()
        if nuovi_giocatori_api:
            for g_api in nuovi_giocatori_api:
                nome_api = g_api['nome']
                norm_api = normalize_str(nome_api)
                
                match_trovato = False
                for idx, row_l in df_listone.iterrows():
                    nome_listone = row_l['Nome']
                    if normalize_str(nome_listone) == norm_api or match_nomi_abbreviati(nome_listone, nome_api):
                        df_listone.loc[idx, 'Squadra'] = g_api['squadra']
                        match_trovato = True
                        break
                
                if not match_trovato and len(nome_api) > 4 and not nome_api.startswith('.'):
                    nuova_riga = {
                        'Id': str(9000 + len(df_listone)),
                        'Nome_Breve': nome_api,
                        'Nome': nome_api,
                        'R': g_api['ruolo'],
                        'Ruolo_Esteso': g_api['ruolo'],
                        'Qt.A': '1',
                        'Qt.I': '1',
                        'Squadra': g_api['squadra'],
                        'FVM': '1.0'
                    }
                    df_listone = pd.concat([df_listone, pd.DataFrame([nuova_riga])], ignore_index=True)
    except Exception as e:
        print(f"⚠️ Avviso API: {e}")

    # Liste per memorizzare le statistiche da incollare nel Master
    fvm_calcolati = []
    pres_list, mv_list, fm_list, gf_list, ass_list, amm_list, esp_list = [], [], [], [], [], [], []

    def safe_int(x):
        try: return int(pd.to_numeric(x, errors='coerce'))
        except: return 0

    def safe_float(x):
        try: return float(pd.to_numeric(str(x).replace(',', '.'), errors='coerce'))
        except: return 0.0

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
        pv, mv_storico, fm_storico, gf, ass, amm, esp = 0, 0.0, 0.0, 0, 0, 0, 0

        # ESTRAZIONE DAL FILE STORICO EXCEL
        best_match = trova_miglior_match_stats(nome, ruolo, df_stats)
        if best_match is not None:
            pv = safe_int(best_match.get('Pv', 0))
            mv_storico = safe_float(best_match.get('Mv', 0.0))
            fm_storico = safe_float(best_match.get('Fm', 0.0))
            gf = safe_int(best_match.get('Gf', 0))
            ass = safe_int(best_match.get('Ass', 0))
            amm = safe_int(best_match.get('Amm', 0))
            esp = safe_int(best_match.get('Esp', 0))
            
            if fm_storico > 0:
                fm_val = fm_storico

        # SE MANCA LO STORICO, USA L'IA SCOUT
        if fm_val is None or fm_val <= 0:
            try: fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
            except: fm_val = None

        # MATEMATICA CORRETTA PER L'FVM
        if fm_val is None:
            if best_qt <= 1:
                is_prospetto = scout.verifica_prospetto_giovanile(nome, squadra)
                base_fvm = 15.0 if is_prospetto else 1.0
            else:
                fm_val = 6.0
                base_fvm = best_qt * 4.0
        else:
            if ruolo == 'A':
                base_fvm = (best_qt * 9.5) + (max(0, fm_val - 5.5) ** 2.2) * 35
            elif ruolo == 'C':
                base_fvm = (best_qt * 7.0) + (max(0, fm_val - 5.5) ** 2.0) * 25
            elif ruolo == 'D':
                base_fvm = (best_qt * 4.0) + (max(0, fm_val - 5.5) ** 1.5) * 15
            elif ruolo == 'P':
                base_fvm = (best_qt * 4.5) + (max(0, fm_val - 5.0) ** 1.5) * 15
            else:
                base_fvm = best_qt * 3.0

            if squadra in BIG_TEAMS and best_qt >= 8.0:
                base_fvm *= 1.20

        fvm_finale = round(min(500.0, max(1.0, float(base_fvm))), 1)
        
        # Salvataggio dati nelle liste
        fvm_calcolati.append(fvm_finale)
        pres_list.append(pv)
        mv_list.append(mv_storico)
        # Se ha giocato all'estero (scout), salva la fanta media proiettata nel CSV per visualizzarla
        fm_list.append(fm_storico if fm_storico > 0 else (round(fm_val, 2) if fm_val else 0.0))
        gf_list.append(gf)
        ass_list.append(ass)
        amm_list.append(amm)
        esp_list.append(esp)

    # ------------------------------------------------------------------
    # AGGIUNTA COLONNE STATISTICHE AL DATAFRAME FINALE MASTER
    # ------------------------------------------------------------------
    df_listone['FVM'] = fvm_calcolati
    df_listone['Pv'] = pres_list
    df_listone['Mv'] = mv_list
    df_listone['Fm'] = fm_list
    df_listone['Gf'] = gf_list
    df_listone['Ass'] = ass_list
    df_listone['Amm'] = amm_list
    df_listone['Esp'] = esp_list

    df_listone = df_listone.fillna("")
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv RIGENERATO CON TUTTE LE STATISTICHE REALI INCLUSE!")

if __name__ == '__main__':
    main()
