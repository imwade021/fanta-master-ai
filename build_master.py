import pandas as pd
from fanta_engine import FantaEngine

def genera_master_db(input_csv, output_csv):
    print("Inizializzazione del Master Engine...")
    motore = FantaEngine()
    
    try:
        # Leggiamo il listone grezzo. 
        # NOTA: Spesso i CSV italiani usano il punto e virgola come separatore.
        df_listone = pd.read_csv(input_csv, sep=';') 
    except FileNotFoundError:
        print(f"ERRORE: File {input_csv} non trovato. Inseriscilo nella cartella per testare.")
        return
    
    # Creiamo le nuove colonne che il tuo Bot Telegram leggerà
    df_listone['P_FM'] = 0.0
    df_listone['Valore_Base_Perc'] = 0.0
    
    print(f"Trovati {len(df_listone)} giocatori nel listone. Inizio calcolo valutazioni...")
    
    # --- IL MOTORE ENTRA IN AZIONE ---
    # Per ora stiamo solo cablando il sistema. Assegneremo una P-FM fittizia 
    # per assicurarci che Pandas e il FantaEngine dialoghino correttamente.
    
    for index, row in df_listone.iterrows():
        # Solitamente nel file di Fantacalcio.it il ruolo è sotto la colonna 'R'
        ruolo = row.get('R', 'A') 
        
        # Test: Simuliamo che un giocatore abbia una P-FM di 7.0
        pfm_test = 7.0 
        
        # Facciamo calcolare la percentuale al nostro motore matematico
        valore_perc = motore.calcola_percentuale_valore(pfm_test, ruolo)
        
        # Scriviamo i risultati direttamente nelle nuove colonne del file
        df_listone.at[index, 'P_FM'] = pfm_test
        df_listone.at[index, 'Valore_Base_Perc'] = valore_perc
        
    # Salviamo il file magico finale
    df_listone.to_csv(output_csv, index=False, sep=';')
    print(f"Lavoro completato! File salvato in: {output_csv}")

if __name__ == "__main__":
    # Assicurati di avere il CSV originale nella stessa cartella per fare il test
    genera_master_db("Lista-FantaAsta-Fantacalcio.csv", "Lista_Finale_Master.csv")
