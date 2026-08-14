import pandas as pd
from fanta_engine import FantaEngine

def genera_master_db(input_csv, output_csv):
    print("Inizializzazione del Master Engine...")
    motore = FantaEngine()
    
    try:
        # Leggiamo il file. Mettiamo header=None perché dallo screen non c'è l'intestazione
        # NOTA: se sul file originale c'è, basterà togliere header=None
        df_listone = pd.read_csv(input_csv, sep=';', header=None) 
    except FileNotFoundError:
        print(f"ERRORE: File {input_csv} non trovato.")
        return
    
    # Rinominiamo le colonne chiave basandoci sugli indici visti nello screenshot
    # 0: ID, 1: Nome, 3: Ruolo, 9: Squadra
    colonne_da_rinominare = {0: 'ID', 1: 'Nome', 3: 'Ruolo', 9: 'Squadra'}
    df_listone.rename(columns=colonne_da_rinominare, inplace=True)
    
    # Creiamo le nuove colonne vuote
    df_listone['P_FM'] = 0.0
    df_listone['Valore_Base_Perc'] = 0.0
    
    print(f"Trovati {len(df_listone)} giocatori. Inizio calcolo...")
    
    for index, row in df_listone.iterrows():
        ruolo = str(row['Ruolo']).strip() # Puliamo eventuali spazi
        
        # --- QUI IN FUTURO METTEREMO I DATI REALI STORICI ---
        # Per ora simuliamo una P-FM di 7.2 per tutti gli attaccanti e 6.2 per gli altri
        pfm_calcolata = 7.2 if ruolo == 'A' else 6.2
        
        # Il motore calcola la percentuale reale matematica
        valore_perc = motore.calcola_percentuale_valore(pfm_calcolata, ruolo)
        
        df_listone.at[index, 'P_FM'] = pfm_calcolata
        df_listone.at[index, 'Valore_Base_Perc'] = valore_perc
        
    df_listone.to_csv(output_csv, index=False, sep=';')
    print(f"File MASTER salvato con successo in: {output_csv}!")

if __name__ == "__main__":
    genera_master_db("Lista-FantaAsta-Fantacalcio.csv", "Lista_Finale_Master.csv")
