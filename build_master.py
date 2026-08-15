import pandas as pd
from fanta_engine import FantaEngine
import math

def genera_master_db(file_listone, file_storico, output_csv):
    print("Inizializzazione del Master Engine...")
    motore = FantaEngine()
    
    try:
        # 1. Carichiamo il listone nuovo dell'anno in corso
        print(f"Lettura del listone: {file_listone}")
        df_listone = pd.read_csv(file_listone, sep=None, engine='python', header=None)
        
        # Rinominiamo le colonne (0: ID, 1: Nome, 3: Ruolo, 9: Squadra)
        df_listone.rename(columns={0: 'ID', 1: 'Nome', 3: 'Ruolo', 9: 'Squadra'}, inplace=True)
        
        # 2. Carichiamo il file storico Excel
        print(f"Lettura dello storico Excel: {file_storico}")
        df_storico = pd.read_excel(file_storico) 
        
        # TRUCCO INFALLIBILE: Trasformiamo tutte le intestazioni in MAIUSCOLO e togliamo gli spazi.
        # Questo risolve tutti i KeyError (es. 'Id', 'id', 'Id ' diventano tutti 'ID').
        df_storico.columns = df_storico.columns.astype(str).str.strip().str.upper()
        
    except Exception as e:
        print(f"ERRORE CRITICO durante il caricamento dei file: {e}")
        return

    print("Incrocio dei dati storici in corso...")
    
    # Pulizia: Assicuriamoci che l'ID sia un numero
    df_listone['ID'] = pd.to_numeric(df_listone['ID'], errors='coerce')
    df_storico['ID'] = pd.to_numeric(df_storico['ID'], errors='coerce')
    
    # 3. MERGE: Uniamo i dati storici al nuovo listone
    # Se il file Excel originale non ha la Fantamedia (FM), creiamo una colonna vuota per evitare blocchi
    if 'FM' not in df_storico.columns:
        print("ATTENZIONE: Colonna 'FM' non trovata nello storico. Uso valori vuoti.")
        df_storico['FM'] = float('nan')

    df_master = pd.merge(df_listone, df_storico[['ID', 'FM']], on='ID', how='left')
    
    # Creiamo le colonne
    df_master['P_FM'] = 0.0
    df_master['Valore_Base_Perc'] = 0.0
    
    print(f"Trovati {len(df_master)} giocatori. Calcolo proiezioni e prezzi...")
    
    # 4. Il Motore analizza ogni singolo giocatore
    for index, row in df_master.iterrows():
        # Prendiamo il ruolo in modo sicuro
        ruolo = str(row.get('Ruolo', 'A')).strip()
        fantamedia_storica = row['FM']
        
        # Gestione Nuovi Arrivi (Dato assente)
        if pd.isna(fantamedia_storica) or math.isnan(fantamedia_storica) or fantamedia_storica == 0:
            pfm_calcolata = 6.0 
        else:
            pfm_calcolata = float(fantamedia_storica)
            
        # Calcolo Prezzo
        valore_perc = motore.calcola_percentuale_valore(pfm_calcolata, ruolo)
        
        df_master.at[index, 'P_FM'] = round(pfm_calcolata, 2)
        df_master.at[index, 'Valore_Base_Perc'] = valore_perc
        
    # 5. Salvataggio
    df_master.to_csv(output_csv, index=False, sep=';')
    print(f"SUCCESSO! File MASTER salvato in: {output_csv}")


if __name__ == "__main__":
    # Nomi esatti dei file
    NOME_FILE_STORICO = "Quotazioni_Fantacalcio_Stagione_2024_25.xlsx"
    NOME_FILE_LISTONE = "Lista-FantaAsta-Fantacalcio.csv"
    NOME_OUTPUT = "Lista_Finale_Master.csv"
    
    genera_master_db(NOME_FILE_LISTONE, NOME_FILE_STORICO, NOME_OUTPUT)
