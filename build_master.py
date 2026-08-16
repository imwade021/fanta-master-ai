import pandas as pd
import numpy as np
import requests
import os
import re
import unicodedata
from scout_engine import ScoutEngine

LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv"
BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna', 'Como']

def normalize_str(s):
    if not isinstance(s, str): return ""
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.lower().split())

def scarica_listone_aggiornato():
    print("📥 Download dell'ultimo listone di mercato in corso...")
    try:
        res = requests.get(LISTONE_URL, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            print("✅ Listone sorgente aggiornato con successo!")
            return True
    except Exception as e:
        print(f"⚠️ Download fallito, uso il file locale esistente: {e}")
    return False

def trova_fantamedia_reale(nome_cercato, df_stats):
    if df_stats.empty: return None
    norm_cercato = normalize_str(nome_cercato)
    
    match = df_stats[df_stats['Nome_Norm'] == norm_cercato]
    if not match.empty: return match.iloc[0].get('Fm', None)
    
    match = df_stats[df_stats['Nome_Norm'].apply(lambda x: norm_cercato in x or x in norm_cercato if isinstance(x, str) else False)]
    if not match.empty: return match.iloc[0].get('Fm', None)
    
    cognome = norm_cercato.split()[0] if norm_cercato else ""
    if len(cognome) > 2:
        match = df_stats[df_stats['Nome_Norm'].str.contains(cognome, regex=False, na=False)]
        if not match.empty: return match.iloc[0].get('Fm', None)
        
    return None

def main():
    print("🚀 Avvio Master Engine - Logica Aggressiva per Semi-Top...")
    
    scarica_listone_aggiornato()
    scout = ScoutEngine()
    
    try:
        # Tenta prima di leggere con il punto e virgola, poi ripiega sulla virgola se fallisce
        try:
            df_listone = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None, sep=';')
            if len(df_listone.columns) < 19:
                df_listone = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None, sep=',')
        except Exception:
            df_listone = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None)

        df_listone.columns = [
            'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
            'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
            'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
        ]
    except Exception as e:
        print(f"❌ Errore caricamento Listone CSV: {e}")
        return

    try:
        df_stats = pd.read_excel("Quotazioni_Fantacalcio_Stagione_2025_26.xlsx", header=1)
        df_stats['Nome_Norm'] = df_stats['Nome'].apply(normalize_str)
    except Exception as e:
        print(f"⚠️ File Statistiche non trovato: {e}")
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row['Nome'])
        ruolo = str(row['R'])
        squadra = str(row.get('Squadra', '')).strip()
        
        # Prendi la quotazione migliore tra Iniziale (Qt.I) e Attuale (Qt.A)
        qt_iniziale = pd.to_numeric(str(row.get('Qt.I', 1)).replace(',', '.'), errors='coerce') or 1.0
        qt_attuale = pd.to_numeric(str(row.get('Qt.A', qt_iniziale)).replace(',', '.'), errors='coerce') or qt_iniziale
        best_qt = max(qt_iniziale, qt_attuale)

        fm_reale_raw = trova_fantamedia_reale(nome, df_stats)
        
        # 1. Storico Italia
        if fm_reale_raw is not None and str(fm_reale_raw).strip() != '':
            try:
                fm_val = float(str(fm_reale_raw).replace(',', '.'))
                if fm_val > 0:
                    fvm_da_fm = max(10.0, (fm_val - 5.0) * 22)
                    fvm_finale = max(best_qt * 1.5, fvm_da_fm)
                else:
                    fm_val = None
            except ValueError:
                fm_val = None
        else:
            fm_val = None

        # 2. Nuovi Acquisti (Molina, Mastantuono, ecc.)
        if fm_val is None:
            fvm_proiettata = scout.calcola_fantamedia_proiettata(nome, ruolo)
            stima_da_fm = max(0, (fvm_proiettata - 5.5) * 30)
            
            if squadra in BIG_TEAMS:
                if best_qt >= 10:
                    floor = 45.0 # Molina andrà qui
                elif best_qt >= 5:
                    floor = 30.0 # Mastantuono (se Qt è salita) andrà qui
                else:
                    floor = 22.0 # Altri
                
                base_valore = max(best_qt * 2.2, stima_da_fm * 1.4, floor)
            else:
                base_valore = max(best_qt * 1.5, stima_da_fm)
                
            fvm_finale = base_valore

        fvm_calcolati.append(round(min(95.0, fvm_finale), 1))

    df_listone['FVM'] = fvm_calcolati
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv rigenerata con Fasce corrette!")

if __name__ == '__main__':
    main()
