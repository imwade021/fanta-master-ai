import requests
from bs4 import BeautifulSoup
import random
import time

class ScoutEngine:
    def __init__(self):
        # I coefficienti di difficoltà dei campionati (1.0 = Difficoltà Serie A)
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
            'Sconosciuto': 0.65 # Valore di default per campionati minori
        }

    def simula_ricerca_dati(self, nome_giocatore):
        """
        Questa è la base dello scraper. Per ora simula una ricerca e restituisce 
        dati plausibili per permetterci di collegarlo al file principale.
        Nel prossimo step la sostituiremo con la vera lettura delle pagine web.
        """
        print(f"🕵️ Scout in azione: Cerco i dati di {nome_giocatore}...")
        
        # Simuliamo un piccolo tempo di attesa per la connessione internet
        time.sleep(0.5) 
        
        # Simulazione di dati trovati su internet (Gol, Assist, Presenze, Campionato)
        dati_trovati = {
            'presenze': random.randint(15, 38),
            'gol': random.randint(0, 12),
            'assist': random.randint(0, 8),
            'ammonizioni': random.randint(0, 10),
            'campionato_origine': random.choice(list(self.coefficienti_campionati.keys()))
        }
        return dati_trovati

    def calcola_fantamedia_proiettata(self, nome_giocatore, ruolo):
        """
        Prende i dati esteri, applica il coefficiente del campionato e 
        restituisce una proiezione realistica per la Serie A.
        """
        dati = self.simula_ricerca_dati(nome_giocatore)
        
        presenze = dati['presenze']
        gol = dati['gol']
        assist = dati['assist']
        malus = dati['ammonizioni'] * 0.5
        campionato = dati['campionato_origine']
        
        # Coefficiente di difficoltà
        coeff = self.coefficienti_campionati.get(campionato, 0.65)
        
        # Calcolo del Bonus totale "scontato" in base alla difficoltà del campionato
        if ruolo == 'A':
            bonus_totale = (gol * 3) + (assist * 1)
        elif ruolo == 'C' or ruolo == 'T':
            bonus_totale = (gol * 3) + (assist * 1)
        elif ruolo == 'D' or ruolo == 'E' or ruolo == 'B':
            bonus_totale = (gol * 3) + (assist * 1)
        else: # Portieri
            bonus_totale = 0 # Tratteremo i portieri a parte se serve
            
        bonus_adattato = bonus_totale * coeff
        
        # Calcolo Voto Base (Simulato: chi gioca tanto prende circa 6, chi fa panchina 5.5)
        voto_base_estero = 6.0 if presenze > 20 else 5.8
        
        # Fantamedia Finale Proiettata
        fantamedia_proiettata = voto_base_estero + (bonus_adattato / presenze) - (malus / presenze)
        
        # Evitiamo valori assurdi (minimo 5.0, massimo 8.5)
        fantamedia_proiettata = max(5.0, min(8.5, fantamedia_proiettata))
        
        print(f"📊 {nome_giocatore} arriva da: {campionato} (Coeff: {coeff})")
        print(f"   Dati: {presenze} Presenze, {gol} Gol, {assist} Assist.")
        print(f"   => P-FM Calcolata: {round(fantamedia_proiettata, 2)}")
        
        return round(fantamedia_proiettata, 2)
