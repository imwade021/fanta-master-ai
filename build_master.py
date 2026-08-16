import pandas as pd
from fanta_engine import FantaEngine
from scout_engine import ScoutEngine
import math

def genera_master_db(file_listone, file_storico, output_csv):
    print("Inizializzazione del Master Engine e dello Scout...")
    motore = FantaEngine()
    scout = ScoutEngine()
    
    try:
        print(f"Lettura del listone: {file_listone}")
        df_listone = pd.read_csv(file_listone, sep=None, engine='python', header=None)
        df_listone.rename(columns={0: 'ID', 1: 'Nome', 3: 'Ruolo', 9: 'Squadra'}, inplace=True)
        
        print(f"Lettura dello storico Excel: {file_storico}")
        df_storico = pd.read_excel(file_storico) 
        df_storico.columns = df_storico.columns.astype(str).str.strip().str.upper()
        
    except Exception as e:
        print(f"ERRORE CRITICO durante il caricamento dei file: {e}")
        return

    print("Incrocio dei dati storici in corso...")
    
    col_id_storico = 'ID'
    if 'ID' not in df_storico.columns:
        col_id_storico = df_storico.columns[0]

    df_listone['ID'] = pd.to_numeric(df_listone['ID'], errors='coerce')
    df_storico[col_id_storico] = pd.to_numeric(df_storico[col_id_storico], errors='coerce')
    
    if 'FM' not in df_storico.columns:
        df_storico['FM'] = float('nan')

    df_master = pd.merge(df_listone, df_storico[[col_id_storico, 'FM']], left_on='ID', right_on=col_id_storico, how='left')
    
    df_master['P_FM'] = 0.0
    df_master['Valore_Base_Perc'] = 0.0
    
    print(f"Trovati {len(df_master)} giocatori. Calcolo proiezioni e prezzi...")
    
    for index, row in df_master.iterrows():
        ruolo = str(row.get('Ruolo', 'A')).strip()
        nome = str(row.get('Nome', 'Sconosciuto')).strip()
        fantamedia_storica = row['FM']
        
        if pd.isna(fantamedia_storica) or math.isnan(fantamedia_storica) or fantamedia_storica == 0:
            pfm_calcolata = scout.calcola_fantamedia_proiettata(nome, ruolo)
        else:
            pfm_calcolata = float(fantamedia_storica)
            
        valore_perc = motore.calcola_percentuale_valore(pfm_calcolata, ruolo)
        
        df_master.at[index, 'P_FM'] = round(pfm_calcolata, 2)
        df_master.at[index, 'Valore_Base_Perc'] = valore_perc
        
    df_master.to_csv(output_csv, index=False, sep=';')
    print(f"SUCCESSO! File MASTER salvato in: {output_csv}")

if __name__ == "__main__":
    # NOME FILE AGGIORNATO ALLA STAGIONE CORRETTA (2025/26)
    NOME_FILE_STORICO = "Quotazioni_Fantacalcio_Stagione_2025_26.xlsx"
    NOME_FILE_LISTONE = "Lista-FantaAsta-Fantacalcio.csv"
    NOME_OUTPUT = "Lista_Finale_Master.csv"
    
    genera_master_db(NOME_FILE_LISTONE, NOME_FILE_STORICO, NOME_OUTPUT)
