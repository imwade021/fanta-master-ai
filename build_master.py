import pandas as pd
import numpy as np
from scout_engine import ScoutEngine

def main():
    print("🚀 Avvio Master Engine con Scouting Integrato...")
    
    # 1. Carichiamo lo ScoutEngine per le API estero
    scout = ScoutEngine()
    
    # 2. Carichiamo il listone principale
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

    # 3. Carichiamo il file delle Statistiche Reali
    try:
        df_stats = pd.read_excel("Quotazioni_Fantacalcio_Stagione_2025_26.xlsx", header=1)
        df_stats['Nome_Clean'] = df_stats['Nome'].astype(str).str.lower().str.strip()
    except Exception as e:
        print(f"⚠️ File Statistiche non trovato, uso solo Scout Engine: {e}")
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    # 4. Elaborazione chirurgica giocatore per giocatore
    for idx, row in df_listone.iterrows():
        nome = str(row['Nome'])
        ruolo = str(row['R'])
        nome_clean = nome.lower().strip()
        
        fvm_finale = None
        
        # Cerca prima nello storico italiano (2025/2026)
        if not df_stats.empty:
            match = df_stats[df_stats['Nome_Clean'] == nome_clean]
            if not match.empty:
                fm_reale = match.iloc[0].get('Fm', None)
                if pd.notnull(fm_reale) and float(str(fm_reale).replace(',', '.')) > 0:
                    fvm_finale = float(str(fm_reale).replace(',', '.'))
        
        # Se NON ha uno storico in Italia (es. Mastantuono dal Real Madrid), intervengono le API dello Scout!
        if fvm_finale is None:
            print(f"🔎 Nuovo acquisto/Esterofilo rilevato: {nome}")
            fvm_proiettata = scout.calcola_fantamedia_proiettata(nome, ruolo)
            
            # Trasformiamo la FantaMedia Proiettata in un valore percentuale FVM credibile per l'asta
            # Es. FM di 7.2 -> ~35-40 FVM | FM di 6.0 -> ~5-10 FVM
            fvm_finale = max(1.0, round((fvm_proiettata - 5.0) * 15, 1))
        
        fvm_calcolati.append(fvm_finale)

    # 5. Sovrascriviamo la colonna FVM con i valori perfetti ed esportiamo
    df_listone['FVM'] = fvm_calcolati
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ File Lista_Finale_Master.csv generato con successo!")

if __name__ == '__main__':
    main()
