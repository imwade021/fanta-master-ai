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
    print("📥 Download listone in corso...")
    try:
        res = requests.get(LISTONE_URL, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            print("✅ Listone scaricato!")
            return True
    except Exception as e:
        print(f"⚠️ Download fallito: {e}")
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
    print("🚀 Avvio Master Engine - V 4.0 (Pulizia Strutturale Estrema)...")
    
    scarica_listone_aggiornato()
    scout = ScoutEngine()
    
    try:
        with open("Lista-FantaAsta-Fantacalcio.csv", "r", encoding="utf-8", errors="ignore") as f:
            prima_riga = f.readline()
        separatore = ';' if ';' in prima_riga else ','
        
        # 1. LETTURA DINAMICA SENZA ASSUNZIONI
        raw_df = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None, sep=separatore, dtype=str, on_bad_lines='skip')
        
        # TROVA L'INTESTAZIONE REALE
        header_idx = -1
        for i, row in raw_df.iterrows():
            row_str = [str(x).lower().strip() for x in row.values]
            if 'nome' in row_str and 'squadra' in row_str:
                header_idx = i
                break
                
        if header_idx == -1:
            print("❌ Errore critico: Impossibile trovare le colonne 'Nome' e 'Squadra' nel CSV.")
            return
            
        # Imposta le vere colonne e butta via la spazzatura sopra l'intestazione
        df_listone = raw_df.iloc[header_idx+1:].copy()
        df_listone.columns = [str(c).strip() for c in raw_df.iloc[header_idx].values]
        
        # 2. FILTRO DI FERRO SUI RUOLI
        if 'R' not in df_listone.columns:
            print("❌ Errore: Colonna 'R' mancante.")
            return
            
        df_listone['R'] = df_listone['R'].astype(str).str.strip().str.upper()
        # Cancella chiunque non sia P, D, C o A (via "Guida", "Serie A", ecc.)
        df_listone = df_listone[df_listone['R'].isin(['P', 'D', 'C', 'A'])]
        
    except Exception as e:
        print(f"❌ Errore di lettura file: {e}")
        return

    try:
        df_stats = pd.read_excel("Quotazioni_Fantacalcio_Stagione_2025_26.xlsx", header=1)
        df_stats['Nome_Norm'] = df_stats['Nome'].apply(normalize_str)
    except Exception:
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row.get('Nome', '')).replace('*', '').strip()
        ruolo = str(row['R'])
        squadra = str(row.get('Squadra', '')).replace('*', '').strip()
        
        # Recupero intelligente delle quotazioni
        qt_iniziale = pd.to_numeric(str(row.get('Qt.I', 1)).replace(',', '.'), errors='coerce')
        if pd.isna(qt_iniziale): qt_iniziale = 1.0
        qt_attuale = pd.to_numeric(str(row.get('Qt.A', qt_iniziale)).replace(',', '.'), errors='coerce')
        if pd.isna(qt_attuale): qt_attuale = qt_iniziale
        
        best_qt = max(qt_iniziale, qt_attuale)
        fm_reale_raw = trova_fantamedia_reale(nome, df_stats)

        # Motore 1: Mercato
        fvm_da_qt = best_qt * (1.1 + (best_qt / 25.0))

        # Motore 2: Campo
        if fm_reale_raw is not None and str(fm_reale_raw).strip() != '':
            try:
                fm_val = float(str(fm_reale_raw).replace(',', '.'))
                fvm_da_fm = max(0, (fm_val - 5.5) ** 2 * 18) if fm_val > 5.5 else max(1.0, best_qt)
            except ValueError:
                fm_val = None
        else:
            fm_val = None

        if fm_val is None:
            try:
                fvm_proiettata = scout.calcola_fantamedia_proiettata(nome, ruolo)
                if fvm_proiettata is None: fvm_proiettata = 5.0
            except:
                fvm_proiettata = 5.0
            fvm_da_fm = max(0, (fvm_proiettata - 5.5) ** 2 * 14) if fvm_proiettata > 5.5 else max(1.0, best_qt)

        base_fvm = max(fvm_da_qt, fvm_da_fm)

        if squadra in BIG_TEAMS and best_qt >= 8.0:
            base_fvm *= 1.15

        try:
            fvm_finale = round(min(95.0, max(1.0, float(base_fvm))), 1)
        except:
            fvm_finale = 1.0

        fvm_calcolati.append(fvm_finale)

    # Scrive la colonna FVM mantenendo intatte e in ordine le colonne del CSV originale
    df_listone['FVM'] = fvm_calcolati
    df_listone = df_listone.fillna(0)
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv generata. Database pulito e allineato!")

if __name__ == '__main__':
    main()
