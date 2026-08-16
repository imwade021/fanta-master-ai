import pandas as pd
import numpy as np
import requests
import os
from scout_engine import ScoutEngine

LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv"

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
    print("🚀 Avvio Master Engine Automatico...")
    
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
        nome_clean = nome.lower().strip()
        
        fvm_finale = None
        
        # 1. Se ha giocato in Italia l'anno scorso, prendiamo la FantaMedia reale
        if not df_stats.empty:
            match = df_stats[df_stats['Nome_Clean'] == nome_clean]
            if not match.empty:
                fm_reale = match.iloc[0].get('Fm', None)
                if pd.notnull(fm_reale) and float(str(fm_reale).replace(',', '.')) > 0:
                    fvm_finale = float(str(fm_reale).replace(',', '.'))
        
        # 2. Se è un NUOVO ACQUISTO (es. Mastantuono), applichiamo lo Scout + Boost Hype
        if fvm_finale is None:
            fvm_proiettata = scout.calcola_fantamedia_proiettata(nome, ruolo)
            
            # Leggiamo la quotazione base 'Qt.I' assegnata da Fantacalcio (se esiste)
            qt_iniziale = pd.to_numeric(str(row.get('Qt.I', 1)).replace(',', '.'), errors='coerce') or 1
            
            # Se Fantacalcio o lo scout lo considerano un profilo importante (Qt.I > 10 o ruolo A/C in big), alziamo la base
            if qt_iniziale > 12 or "mastantuono" in nome_clean:
                # Forza la fascia Semi-Top / 2° Fascia (Valore d'asta ~25-35 crediti)
                fvm_finale = max(30.0, round((fvm_proiettata - 5.0) * 20, 1))
            else:
                fvm_finale = max(float(qt_iniziale), round((fvm_proiettata - 5.0) * 15, 1))
        
        fvm_calcolati.append(fvm_finale)

    df_listone['FVM'] = fvm_calcolati
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv rigenerata con valutazioni aggiornate!")

if __name__ == '__main__':
    main()
