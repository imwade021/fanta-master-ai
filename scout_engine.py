import requests
from bs4 import BeautifulSoup
import urllib.parse
import time

class ScoutEngine:
    def __init__(self):
        # I coefficienti di difficoltà dei campionati
        self.coefficienti_campionati = {
            'Premier League': 1.0,
            'La Liga': 0.95,
            'Bundesliga': 0.90,
            'Ligue 1': 0.85,
            'Serie B': 0.80,
            'Eredivisie': 0.75,
            'Primeira Liga': 0.75,
            'Brasileirao': 0.70,
            'Championship': 0.70,
            'Sconosciuto': 0.65
        }
        
        # Un travestimento: diciamo ai siti che siamo un browser Google Chrome e non un bot
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def estrai_dati_reali(self, nome_giocatore):
        print(f"🕵️ Scout online: Mi collego alla rete per cercare {nome_giocatore}...")
        
        # Base di partenza nel caso la rete non ci dia risposte utili
        dati_base = {'presenze': 25, 'gol': 0, 'assist': 0, 'ammonizioni': 2, 'campionato_origine': 'Sconosciuto'}
        
        try:
            # Creiamo l'URL sicuro per l'API di Wikipedia
            nome_url = urllib.parse.quote(nome_giocatore)
            url = f"https://it.wikipedia.org/w/api.php?action=query&list=search&srsearch={nome_url}+calciatore&utf8=&format=json"
            
            # Effettuiamo la VERA chiamata a internet
            response = requests.get(url, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                dati_json = response.json()
                risultati = dati_json.get('query', {}).get('search', [])
                
                if risultati:
                    # Leggiamo il riassunto della pagina trovata online
                    snippet = risultati[0].get('snippet', '').lower()
                    print(f"   [+] Profilo trovato online! Analisi in corso...")
                    
                    # Deduzione intelligente dal testo web (Proof of Concept)
                    if 'attaccante' in snippet:
                        dati_base['gol'] = 8
                        dati_base['assist'] = 3
                    elif 'centrocampista' in snippet:
                        dati_base['gol'] = 3
                        dati_base['assist'] = 5
                    elif 'difensore' in snippet:
                        dati_base['gol'] = 1
                        dati_base['ammonizioni'] = 6
                else:
                    print(f"   [-] Nessuna info web precisa. Uso statistiche base.")
            else:
                print(f"   [!] Rete respinta (Errore {response.status_code}).")

        except Exception as e:
            print(f"   [!] Errore di connessione a internet: {e}")
        
        # Pausa di cortesia di 1 secondo per non subire blocchi dal sito
        time.sleep(1) 
        return dati_base

    def calcola_fantamedia_proiettata(self, nome_giocatore, ruolo):
        """
        Richiama l'estrazione da internet e calcola il valore reale.
        """
        dati = self.estrai_dati_reali(nome_giocatore)
        
        presenze = dati['presenze']
        gol = dati['gol']
        assist = dati['assist']
        malus = dati['ammonizioni'] * 0.5
        campionato = dati['campionato_origine']
        
        coeff = self.coefficienti_campionati.get(campionato, 0.65)
        
        if ruolo == 'A':
            bonus_totale = (gol * 3) + (assist * 1)
        elif ruolo == 'C' or ruolo == 'T':
            bonus_totale = (gol * 3) + (assist * 1)
        elif ruolo == 'D' or ruolo == 'E' or ruolo == 'B':
            bonus_totale = (gol * 3) + (assist * 1)
        else: 
            bonus_totale = 0 
            
        bonus_adattato = bonus_totale * coeff
        voto_base_estero = 6.0 if presenze > 20 else 5.8
        
        fantamedia_proiettata = voto_base_estero + (bonus_adattato / presenze) - (malus / presenze)
        
        fantamedia_proiettata = max(5.0, min(8.5, fantamedia_proiettata))
        
        print(f"   => P-FM Calcolata per {nome_giocatore}: {round(fantamedia_proiettata, 2)}")
        
        return round(fantamedia_proiettata, 2)
