import pandas as pd
import numpy as np
import requests
import os
import re
import unicodedata
from scout_engine import ScoutEngine

LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv"
BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna', 'Como']

def normalize_and_tokenize(s):
    if not isinstance(s, str): return set()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return set(s.split())

def scarica_listone_aggiornato():
    try:
        res = requests.get(LISTONE_URL, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            return True
    except:
        pass
    return False

def trova_fantamedia_reale(nome_cercato, df_stats):
    if df_stats.empty: return None
    tokens_cercato = normalize_and_tokenize(nome_cercato)
    if not tokens_cercato: return None

    for idx, row in df_stats.iterrows():
        tokens_stat = row.get('Tokens', set())
        if not tokens_stat: continue
        if tokens_cercato == tokens_stat:
            return row.get('Fm', None)
        overlap = tokens_cercato.intersection(tokens_stat)
        if len(overlap) >= 2 or (len(overlap) == 1 and any(len(w) >= 5 for w in overlap)):
            return row.get('Fm', None)
    return None

def main():
    print("🚀 Avvio Master Engine - PARSER MANUALE ANTIPROIETTILE...")
    
    scarica_listone_aggiornato()
    scout = ScoutEngine()
    
    # -------------------------------------------------------------------
    # LETTURA MANUALE: Bypassa tutti gli errori di formattazione del CSV
    # -------------------------------------------------------------------
    valid_data = []
    try:
        with open("Lista-FantaAsta-Fantacalcio.csv", "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        header_found = False
        sep = ','
        
        for line in lines:
            line_clean = line.strip()
            if not line_clean: continue
            
            # Cerca l'inizio reale della tabella
            if not header_found:
                if 'nome' in line_clean.lower() and 'squadra' in line_clean.lower():
                    header_found = True
                    sep = ';' if ';' in line_clean else ','
                continue
                
            parts = line_clean.split(sep)
            if len(parts) >= 10:
                ruolo = parts[3].strip().upper()
                # FILTRO ASSOLUTO: Se non è P, D, C, A, la riga viene distrutta
                if ruolo in ['P', 'D', 'C', 'A']:
                    row_data = parts[:19]
                    while len(row_data) < 19:
                        row_data.append("")
                    valid_data.append(row_data)
    except Exception as e:
        print(f"❌ Errore lettura manuale: {e}")
        return

    if not valid_data:
        print("❌ Nessun giocatore valido trovato. CSV illeggibile.")
        return

    df_listone = pd.DataFrame(valid_data, columns=[
        'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
        'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
        'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
    ])
    print(f"✅ Trovati {len(df_listone)} giocatori reali.")

    try:
        df_stats = pd.read_excel("Quotazioni_Fantacalcio_Stagione_2025_26.xlsx", header=1)
        df_stats['Tokens'] = df_stats['Nome'].apply(normalize_and_tokenize)
    except Exception:
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row.get('Nome', '')).replace('*', '').strip()
        ruolo = str(row['R'])
        squadra = str(row.get('Squadra', '')).replace('*', '').strip()
        
        # Protezione valori astronomici
        try:
            qt_iniziale = float(str(row.get('Qt.I', '1')).replace(',', '.'))
        except:
            qt_iniziale = 1.0
        if qt_iniziale > 150: qt_iniziale = 1.0
        
        try:
            qt_attuale = float(str(row.get('Qt.A', qt_iniziale)).replace(',', '.'))
        except:
            qt_attuale = qt_iniziale
        if qt_attuale > 150: qt_attuale = qt_iniziale
        
        best_qt = max(qt_iniziale, qt_attuale)
        fm_reale_raw = trova_fantamedia_reale(nome, df_stats)

        fm_val = None
        if fm_reale_raw is not None and str(fm_reale_raw).strip() != '':
            try:
                fm_val = float(str(fm_reale_raw).replace(',', '.'))
            except:
                pass

        if fm_val is None:
            try:
                fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
                if fm_val is None: fm_val = 5.0
            except:
                fm_val = 5.0

        # Calcolo FVM Corretto
        fvm_da_qt = best_qt * 1.5
        if fm_val > 5.5:
            fvm_da_fm = (fm_val - 5.2) ** 2 * 12
        else:
            fvm_da_fm = max(1.0, best_qt)
            
        base_fvm = max(fvm_da_qt, fvm_da_fm)

        if squadra in BIG_TEAMS and best_qt >= 8.0:
            base_fvm *= 1.15

        try:
            fvm_finale = round(min(95.0, max(1.0, float(base_fvm))), 1)
        except:
            fvm_finale = 1.0

        fvm_calcolati.append(fvm_finale)

    df_listone['FVM'] = fvm_calcolati
    df_listone = df_listone.fillna(0)
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ File CSV esportato correttamente!")

if __name__ == '__main__':
    main()
