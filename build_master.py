import pandas as pd
import numpy as np
import requests
import os
from scout_engine import ScoutEngine

LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv"

# Club di prima fascia che aumentano l'hype e il prezzo base dei nuovi acquisti
BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna']

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

def main():
    print("🚀 Avvio Master Engine Automatico e Dinamico...")
    
    scarica_listone_aggiornato()
    scout = ScoutEngine()
    
    try:
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
        df_stats['Nome_Clean'] = df_stats['Nome'].astype(str).str.lower().str.strip()
    except Exception as e:
        print(f"⚠️ File Statistiche non trovato: {e}")
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row['Nome'])
        ruolo = str(row['R'])
        squadra = str(row.get('Squadra', '')).strip()
        nome_clean = nome.lower().strip()
        
        fvm_finale = None
        
        # 1. Se ha giocato in Serie A l'anno scorso (2025/26), prendiamo la FantaMedia reale
        if not df_stats.empty:
            match = df_stats[df_stats['Nome_Clean'] == nome_clean]
            if not match.empty:
                fm_reale = match.iloc[0].get('Fm', None)
                if pd.notnull(fm_reale) and float(str(fm_reale).replace(',', '.')) > 0:
                    fvm_finale = float(str(fm_reale).replace(',', '.'))
        
        # 2. Se è un NUOVO ACQUISTO (es. Molina, Mastantuono, Spence, Pinco Pallino...)
        if fvm_finale is None:
            # Recuperiamo la quotazione iniziale ufficiale Fantacalcio
            qt_iniziale = pd.to_numeric(str(row.get('Qt.I', 1)).replace(',', '.'), errors='coerce') or 1.0
            
            # Calcoliamo la FantaMedia proiettata tramite Scout Engine
            fvm_proiettata = scout.calcola_fantamedia_proiettata(nome, ruolo)
            
            # Stima base d'asta ricavata dalla FantaMedia
            stima_da_fm = (fvm_proiettata - 5.0) * 18
            
            # MOLTIPLICATORE DINAMICO DI SQUADRA (Hype / Status del Club)
            # Se va in una Big di Serie A, il prezzo minimo d'asta sale automaticamente
            factor_squadra = 1.35 if squadra in BIG_TEAMS else 1.0
            
            # La FVM finale prende IL VALORE PIÙ ALTO tra:
            # - La quotazione iniziale di Fantacalcio (riproporzionata per le Big)
            # - La stima calcolata dalle API dello Scout
            base_valore = max(qt_iniziale * 1.5, stima_da_fm) * factor_squadra
            
            # Garantiamo un valore coerente tra 1 e 100
            fvm_finale = max(qt_iniziale, round(base_valore, 1))
            fvm_finale = min(95.0, fvm_finale)
            
            print(f"   [+] Nuovo Acquisto: {nome} ({squadra}) => Quot.Iniziale: {qt_iniziale} | FVM Calcolata: {fvm_finale}")

        fvm_calcolati.append(fvm_finale)

    # Aggiorniamo il listone e salviamo il file master
    df_listone['FVM'] = fvm_calcolati
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv generata in modo 100% automatico!")

if __name__ == '__main__':
    main()
