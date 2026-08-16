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
    print("🚀 Avvio Master Engine - V 2.0 (Blindato)...")
    
    scarica_listone_aggiornato()
    scout = ScoutEngine()
    
    try:
        # [🛡️ SISTEMA 5] LETTURA ANTIPROIETTILE CON AUTO-REGOLAZIONE
        with open("Lista-FantaAsta-Fantacalcio.csv", "r", encoding="utf-8", errors="ignore") as f:
            prima_riga = f.readline()
        
        separatore = ';' if ';' in prima_riga else ','
        
        # skip_bad_lines evita che una singola riga corrotta distrugga tutto il file
        df_listone = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None, sep=separatore, on_bad_lines='skip')
        
        if len(df_listone.columns) > 19:
            df_listone = df_listone.iloc[:, :19]
        while len(df_listone.columns) < 19:
            df_listone[len(df_listone.columns)] = ""

        df_listone.columns = [
            'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
            'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
            'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
        ]
    except Exception as e:
        print(f"❌ Errore critico caricamento Listone CSV: {e}")
        return

    try:
        df_stats = pd.read_excel("Quotazioni_Fantacalcio_Stagione_2025_26.xlsx", header=1)
        df_stats['Nome_Norm'] = df_stats['Nome'].apply(normalize_str)
    except Exception as e:
        print(f"⚠️ File Statistiche non trovato: {e}")
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        # [🛡️ SISTEMA 3] PULIZIA ASTERISCHI E "NaN"
        nome_raw = str(row['Nome'])
        if nome_raw.lower() == 'nan' or nome_raw.strip() == '':
            fvm_calcolati.append(0)
            continue
            
        nome = nome_raw.replace('*', '').strip()
        ruolo = str(row['R']).replace('*', '').strip()
        squadra = str(row.get('Squadra', '')).replace('*', '').strip()
        
        qt_iniziale = pd.to_numeric(str(row.get('Qt.I', 1)).replace(',', '.'), errors='coerce')
        if pd.isna(qt_iniziale): qt_iniziale = 1.0
        
        qt_attuale = pd.to_numeric(str(row.get('Qt.A', qt_iniziale)).replace(',', '.'), errors='coerce')
        if pd.isna(qt_attuale): qt_attuale = qt_iniziale
        
        best_qt = max(qt_iniziale, qt_attuale)

        fm_reale_raw = trova_fantamedia_reale(nome, df_stats)
        
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

        if fm_val is None:
            # [🛡️ SISTEMA 2] SCUDO API
            try:
                fvm_proiettata = scout.calcola_fantamedia_proiettata(nome, ruolo)
                if fvm_proiettata is None: fvm_proiettata = 5.0
            except Exception as e:
                print(f"   [!] Errore API per {nome}, applico paracadute. Dettagli: {e}")
                fvm_proiettata = 5.0

            stima_da_fm = max(0, (fvm_proiettata - 5.5) * 30)
            
            # [🛡️ SISTEMA 1] PRIMAVERA LOCK
            if best_qt <= 1.0 and fvm_proiettata <= 5.2:
                print(f"   [👶] Primavera Lock attivato per {nome}: FVM bloccato a 1.0")
                fvm_finale = 1.0
            
            # BIG TEAM BOOST
            elif squadra in BIG_TEAMS:
                if best_qt >= 10:
                    floor = 45.0
                elif best_qt >= 5:
                    floor = 30.0
                else:
                    floor = 15.0 # Meno aggressivo per le semplici riserve
                
                base_valore = max(best_qt * 2.2, stima_da_fm * 1.4, floor)
                fvm_finale = base_valore
                
            # [🛡️ SISTEMA 4] BOOST TITOLARI DI PROVINCIA
            else:
                if best_qt >= 8:
                    floor = 15.0 # Se costa 8+ crediti in provincia, è titolare: va in 3a fascia
                    base_valore = max(best_qt * 1.8, stima_da_fm * 1.2, floor)
                else:
                    base_valore = max(best_qt * 1.5, stima_da_fm)
                
                fvm_finale = base_valore

        # Convertitore di sicurezza finale per rimuovere eventuali NaN fantasma
        try:
            if pd.isna(fvm_finale): fvm_finale = 1.0
            fvm_finale = round(min(95.0, float(fvm_finale)), 1)
        except:
            fvm_finale = 1.0

        fvm_calcolati.append(fvm_finale)

    df_listone['FVM'] = fvm_calcolati
    
    # Riempie con 0 eventuali celle vuote rimaste nel dataset
    df_listone = df_listone.fillna(0)
    
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv generata con Sicurezza V2.0!")

if __name__ == '__main__':
    main()
