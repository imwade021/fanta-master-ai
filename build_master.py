import pandas as pd
from fanta_engine import FantaEngine

def genera_master_db(file_listone, file_storico, output_csv):
    print("Inizializzazione del Master Engine...")
    motore = FantaEngine()
    
    try:
        # 1. Carichiamo il listone nuovo dell'anno in corso
        df_listone = pd.read_csv(file_listone, sep=';', header=None)
        # Assicurati che gli indici (0, 1, 3, 9) corrispondano alle tue colonne reali
        df_listone.rename(columns={0: 'ID', 1: 'Nome', 3: 'Ruolo', 9: 'Squadra'}, inplace=True)
        
        # 2. Carichiamo il file storico (quello che hai appena caricato)
        # NB: Se il file è un Excel usa read_excel, se è un csv usa read_csv
        df_storico = pd.read_excel(file_storico) 
        
        # Uniformiamo il nome della colonna ID per farli combaciare
        # Assumiamo che nel file storico l'ID si chiami 'Id' (con la i maiuscola)
        df_storico.rename(columns={'Id': 'ID'}, inplace=True)
        
    except Exception as e:
        print(f"ERRORE durante il caricamento dei file: {e}")
        return

    print("Incrocio dei dati in corso...")
    
    # 3. IL MERGE MAGICO
    # Uniamo il listone con la colonna 'Fm' (Fantamedia) dello storico usando l'ID.
    # 'how=left' significa: tieni tutti i giocatori del listone nuovo, anche se non ci sono nello storico.
    df_master = pd.merge(df_listone, df_storico[['ID', 'Fm']], on='ID', how='left')
    
    # Prepariamo le colonne per l'output
    df_master['P_FM'] = 0.0
    df_master['Valore_Base_Perc'] = 0.0
    
    print(f"Trovati {len(df_master)} giocatori. Inizio calcolo proiezioni...")
    
    # 4. Il motore analizza ogni giocatore
    for index, row in df_master.iterrows():
        ruolo = str(row['Ruolo']).strip()
        fantamedia_storica = row['Fm']
        
        # Controllo: il giocatore ha una Fantamedia nello storico?
        if pd.isna(fantamedia_storica):
            # IL DATO MANCA (Nuovo arrivo o Serie B)
            # Qui si accenderà l'Auto-Scouting! Per ora impostiamo un voto base fittizio.
            pfm_calcolata = 6.0 
        else:
            # GIOCATORE GIÀ IN SERIE A
            # Usiamo la sua vera Fantamedia dell'anno scorso!
            pfm_calcolata = float(fantamedia_storica)
            
        # Il motore calcola la percentuale reale matematica (per ora solo per gli attaccanti nel nostro script test)
        valore_perc = motore.calcola_percentuale_valore(pfm_calcolata, ruolo)
        
        df_master.at[index, 'P_FM'] = pfm_calcolata
        df_master.at[index, 'Valore_Base_Perc'] = valore_perc
        
    # Salviamo il file finale
    df_master.to_csv(output_csv, index=False, sep=';')
    print(f"File MASTER salvato con successo in: {output_csv}!")

if __name__ == "__main__":
    # IMPORTANTE: Sostituisci i nomi qui sotto con i nomi ESATTI dei tuoi file su GitHub
    genera_master_db("Lista-FantaAsta-Fantacalcio.csv", "Quotazioni_Fantacalcio_NOMECOMPLETO.xlsx", "Lista_Finale_Master.csv")
