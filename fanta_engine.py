class FantaEngine:
    def __init__(self):
        # Coefficienti di difficoltà delle leghe rispetto alla Serie A (1.0).
        # Le chiavi seguono i nomi restituiti da API-Football.
        self.coeff_leghe = {
            'serie a': 1.00,
            'premier league': 1.05,
            'la liga': 0.95,
            'bundesliga': 0.90,
            'ligue 1': 0.85,
            'eredivisie': 0.75,
            'primeira liga': 0.75,
            'liga portugal': 0.75,
            'serie b': 0.70,
            'championship': 0.70,
            'uefa champions league': 1.05,
            'uefa europa league': 0.90,
            'coppa italia': 0.90,
        }
        
        # Fattore squadra in Serie A (moltiplicatore in base a dove viene comprato)
        self.fattore_squadra = {
            'Top': 1.15,   # Inter, Juve, Milan, Napoli, Atalanta
            'Media': 1.0,  # Fiorentina, Lazio, Roma, Torino...
            'Bassa': 0.85  # Neopromosse, squadre in lotta salvezza
        }

        # Ancore per l'assegnazione della Percentuale di Budget (Esempio per Attaccanti)
        # Formato: { P-FM : Percentuale_Budget }
        self.ancore_attaccanti = {
            8.5: 16.0,  # Top Assoluto (es. Lautaro)
            7.8: 12.0,  # Primo Slot (es. Leao)
            7.2: 7.0,   # Secondo Slot (es. Retegui)
            6.8: 4.0,   # Terzo Slot (es. Pinamonti)
            6.2: 1.0,   # Scommessa
            0.0: 0.1    # Base minima
        }

    def calcola_pfm_estero(self, presenze, gol, assist, lega, fascia_squadra_destinazione):
        """
        Converte le statistiche di un giocatore proveniente dall'estero in una Fantamedia Proiettata (P-FM)
        """
        if presenze == 0:
            return 6.0 # Voto base se non ha mai giocato
            
        # 1. Calcolo Voto Base (Chi gioca molto ha un voto base leggermente più alto)
        voto_base = 6.0 + (presenze * 0.005) 
        
        # 2. Calcolo Bonus medi a partita
        media_gol_partita = gol / presenze
        media_assist_partita = assist / presenze
        punti_bonus = (media_gol_partita * 3) + (media_assist_partita * 1)
        
        # 3. Fantamedia Grezza
        fm_grezza = voto_base + punti_bonus
        
        # 4. Applicazione dei Moltiplicatori
        c_lega = self.coeff_leghe.get(str(lega).strip().lower(), 0.8)  # lega non nota -> 0.8
        f_squadra = self.fattore_squadra.get(fascia_squadra_destinazione, 1.0)
        
        # Il coefficiente lega pesa i BONUS, non il voto: cambiare campionato non
        # abbassa il voto d'ufficio. Applicandolo a tutta la fantamedia, un 6.78
        # in Ligue 1 diventava 5.77, sotto la media di ruolo della Serie A.
        pfm_finale = voto_base + (punti_bonus * c_lega * f_squadra)
        
        # Arrotondiamo a 2 decimali
        return round(pfm_finale, 2)

    def calcola_percentuale_valore(self, pfm_giocatore, ruolo):
        """
        Interpola la P-FM del giocatore con le Ancore per restituire la % di budget consigliata
        """
        if ruolo != 'A':
            return 1.0 # Per ora implementiamo solo gli attaccanti come test
            
        ancore = self.ancore_attaccanti
        pfm_ordinate = sorted(ancore.keys())
        
        # Se la P-FM è altissima, oltre il top assoluto
        if pfm_giocatore >= pfm_ordinate[-1]:
            return ancore[pfm_ordinate[-1]]
            
        # Se è bassissima
        if pfm_giocatore <= pfm_ordinate[0]:
            return ancore[pfm_ordinate[0]]
            
        # Interpolazione lineare per trovare il valore esatto in mezzo alle ancore
        for i in range(len(pfm_ordinate) - 1):
            pfm_sotto = pfm_ordinate[i]
            pfm_sopra = pfm_ordinate[i+1]
            
            if pfm_sotto <= pfm_giocatore <= pfm_sopra:
                perc_sotto = ancore[pfm_sotto]
                perc_sopra = ancore[pfm_sopra]
                
                # Calcolo proporzione matematica
                diff_pfm = pfm_sopra - pfm_sotto
                diff_perc = perc_sopra - perc_sotto
                ratio = (pfm_giocatore - pfm_sotto) / diff_pfm
                
                valore_finale = perc_sotto + (diff_perc * ratio)
                return round(valore_finale, 1)


# --- TESTIAMO IL MOTORE ---
if __name__ == "__main__":
    motore = FantaEngine()
    
    # Esempio: Artem Dovbyk arriva dalla Liga (Girona) alla Roma (Fascia Media)
    # Stats Liga: 36 presenze, 24 gol, 8 assist
    pfm_dovbyk = motore.calcola_pfm_estero(presenze=36, gol=24, assist=8, lega='La Liga', fascia_squadra_destinazione='Media')
    
    valore_perc_dovbyk = motore.calcola_percentuale_valore(pfm_dovbyk, ruolo='A')
    
    print(f"--- ANALISI NUOVO ARRIVO ---")
    print(f"Fantamedia Proiettata (P-FM) in Serie A: {pfm_dovbyk}")
    print(f"Percentuale di Budget Consigliata: {valore_perc_dovbyk}%")
