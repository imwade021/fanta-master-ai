import os
import re
import time
import json
import unicodedata
import requests

from fanta_engine import FantaEngine

LEAGUE_SERIE_A = 135
LEAGUE_SERIE_B = 136

# Stagione appena conclusa (2025 = 2025/26): e' quella da cui si proietta l'asta.
# Il piano free non la copre (si ferma al 2024): in quel caso si ripiega
# automaticamente sulla stagione precedente, segnalandolo nel log.
SEASON_STATS = int(os.getenv("FANTA_SEASON_STATS", "2025"))
SEASON_CORRENTE = int(os.getenv("FANTA_SEASON", "2026"))

MAX_LOOKUP = int(os.getenv("FANTA_MAX_LOOKUP", "50"))

# Il piano free consente ~10 chiamate al minuto: senza pausa si prende HTTP 429.
PAUSA_CHIAMATE = float(os.getenv("FANTA_PAUSA", "6.5"))
ATTESA_DOPO_429 = float(os.getenv("FANTA_ATTESA_429", "60"))
MAX_429_CONSECUTIVI = 3
CACHE_FILE = "scout_cache.json"

# Le squadre NON sono piu' hardcoded: si ricavano dal listone Fantacalcio della
# stagione corrente (colonna Squadra). Cosi' promozioni e retrocessioni si
# aggiornano da sole. Gli Id API vengono risolti una volta e messi in cache.

# Id noti e stabili (l'API non li cambia). Servono da rete di sicurezza.
TEAM_ID_NOTI = {
    'inter': 505, 'milan': 489, 'juventus': 496, 'napoli': 492,
    'roma': 497, 'atalanta': 499, 'lazio': 487, 'fiorentina': 502,
    'bologna': 500, 'torino': 503, 'udinese': 494, 'genoa': 495,
    'verona': 504, 'cagliari': 490, 'lecce': 867, 'como': 1020,
    'parma': 523
}

ALIAS_SQUADRE = {
    'hellas verona': 'Verona', 'ac milan': 'Milan', 'as roma': 'Roma',
    'ssc napoli': 'Napoli', 'fc internazionale': 'Inter', 'inter': 'Inter',
    'us lecce': 'Lecce', 'us cremonese': 'Cremonese', 'ac pisa': 'Pisa',
    'us sassuolo': 'Sassuolo', 'sassuolo': 'Sassuolo', 'pisa': 'Pisa',
    'cremonese': 'Cremonese',
}


def normalize_str(s):
    if not isinstance(s, str):
        s = str(s or "")
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return " ".join(s.split())


def nome_squadra_listone(nome_api):
    return ALIAS_SQUADRE.get(normalize_str(nome_api), str(nome_api).strip())


class ScoutEngine:
    def __init__(self):
        self.api_key = (
            os.getenv("FOOTBALL_API_KEY") or
            os.getenv("API_FOOTBALL_KEY") or
            os.getenv("RAPIDAPI_KEY")
        )
        self.base_url = "https://v3.football.api-sports.io"
        self.engine = FantaEngine()

        self.serie_a_teams = {}
        self.mappa_api_id = {}
        self.chiamate = 0
        self.season_stats = SEASON_STATS
        self.season_declassata = False
        self.quota_esaurita = False      # interruttore: si spegne tutto al primo "limit reached"
        self.errori_429 = 0
        self._ultima_chiamata = 0.0
        self.cache = self._carica_cache()

    # ------------------------------------------------------------------
    # CACHE
    # ------------------------------------------------------------------
    def _carica_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    dati = json.load(f)
                    dati.setdefault("stats", {})
                    dati.setdefault("team_ids", {})
                    return dati
            except Exception:
                pass
        return {"stats": {}, "team_ids": {}}

    def salva_cache(self):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=1, sort_keys=True)
        except Exception as e:
            print(f"⚠️ Impossibile salvare la cache: {e}")

    # ------------------------------------------------------------------
    # CHIAMATA BASE -> (risposta, stato)
    # stato: 'ok' | 'quota' | 'piano' | 'errore'
    # ------------------------------------------------------------------
    def _get(self, endpoint, params, timeout=10):
        if not self.api_key or self.quota_esaurita:
            return [], 'errore'

        # Rispetta il limite al minuto: aspetta se l'ultima chiamata e' troppo recente
        trascorso = time.time() - self._ultima_chiamata
        if self._ultima_chiamata and trascorso < PAUSA_CHIAMATE:
            time.sleep(PAUSA_CHIAMATE - trascorso)
        self._ultima_chiamata = time.time()

        self.chiamate += 1
        try:
            res = requests.get(
                f"{self.base_url}/{endpoint}",
                headers={'x-apisports-key': self.api_key},
                params=params,
                timeout=timeout
            )
        except Exception as e:
            print(f"⚠️ Errore rete su /{endpoint}: {e}")
            return [], 'errore'

        if res.status_code == 429:
            # Troppe richieste al minuto: aspetta e riprova una volta sola
            self.errori_429 += 1
            if self.errori_429 >= MAX_429_CONSECUTIVI:
                print("🛑 HTTP 429 ripetuti: limite di frequenza non gestibile, interrompo.")
                self.quota_esaurita = True
                return [], 'quota'
            print(f"⏳ HTTP 429 su /{endpoint}: attendo {ATTESA_DOPO_429:.0f}s e riprovo...")
            time.sleep(ATTESA_DOPO_429)
            self._ultima_chiamata = time.time()
            return self._get(endpoint, params, timeout)

        if res.status_code != 200:
            print(f"⚠️ /{endpoint}: HTTP {res.status_code}")
            return [], 'errore'

        try:
            data = res.json()
        except Exception:
            return [], 'errore'

        # L'API risponde 200 anche sugli errori: il motivo sta nel campo 'errors'.
        errori = data.get('errors')
        if errori and not isinstance(errori, list):
            testo = " ".join(str(v) for v in errori.values()).lower()
            if 'request limit' in testo or 'requests' in errori:
                if not self.quota_esaurita:
                    print("🛑 Quota giornaliera API esaurita: interrompo le chiamate "
                          "(il resto viene calcolato dai dati locali).")
                self.quota_esaurita = True
                return [], 'quota'
            if 'plan' in errori:
                print(f"⚠️ /{endpoint} non incluso nel piano: {errori.get('plan')}")
                return [], 'piano'
            print(f"⚠️ /{endpoint} errore API: {errori}")
            return [], 'errore'

        self.errori_429 = 0      # una risposta buona azzera il contatore
        return data.get('response', []) or [], 'ok'

    # ------------------------------------------------------------------
    # RISOLUZIONE ID SQUADRE (una volta sola, poi da cache)
    # ------------------------------------------------------------------
    def carica_squadre_serie_a(self, nomi_squadre=None):
        nomi_squadre = [n for n in (nomi_squadre or []) if n and str(n).strip()]
        if not nomi_squadre:
            print("⚠️ Nessuna squadra ricavata dal listone: rose non sincronizzabili.")
            self.serie_a_teams = {}
            return {}

        squadre, da_risolvere = {}, []

        for nome in nomi_squadre:
            chiave = normalize_str(nome)
            tid = self.cache["team_ids"].get(chiave) or TEAM_ID_NOTI.get(chiave)
            if tid:
                squadre[nome] = tid
            else:
                da_risolvere.append(nome)

        # Le neopromosse non sono fra gli Id noti: le cerco in Serie A e in Serie B
        # dell'ultima stagione coperta dal piano. Due chiamate, poi restano in cache.
        if da_risolvere:
            print(f"🔎 Risoluzione Id per: {', '.join(da_risolvere)}")
            trovati = {}
            for lega in (LEAGUE_SERIE_A, LEAGUE_SERIE_B):
                risposta, stato = self._get("teams", {'league': lega, 'season': self.season_stats})
                if stato == 'piano':
                    risposta, stato = self._get("teams", {'league': lega, 'season': self.season_stats - 1})
                if stato != 'ok':
                    continue
                for item in risposta:
                    team = item.get('team', {})
                    if team.get('id') and team.get('name'):
                        trovati[normalize_str(nome_squadra_listone(team['name']))] = team['id']

            for nome in list(da_risolvere):
                tid = trovati.get(normalize_str(nome))
                if tid:
                    squadre[nome] = tid
                    self.cache["team_ids"][normalize_str(nome)] = tid
                    da_risolvere.remove(nome)

            if da_risolvere:
                print(f"⚠️ Id non risolti (rose non scaricabili): {', '.join(da_risolvere)}")

        self.serie_a_teams = squadre
        print(f"✅ Squadre Serie A {SEASON_CORRENTE}/{str(SEASON_CORRENTE + 1)[-2:]}: "
              f"{len(squadre)} su {len(nomi_squadre)} con Id valido.")
        return squadre

    # ------------------------------------------------------------------
    # ROSE (endpoint senza parametro season: funziona anche sul piano free)
    # ------------------------------------------------------------------
    def sincronizza_rose_serie_a(self):
        if not self.api_key:
            print("⚠️ API Key non trovata. Sincronizzazione rose saltata.")
            return []

        if not self.serie_a_teams:
            self.carica_squadre_serie_a()

        nuovi_giocatori, vuote = [], []
        print("📡 Scansione rose in corso...")

        for squadra, team_id in self.serie_a_teams.items():
            if self.quota_esaurita:
                vuote.append(squadra)
                continue

            risposta, stato = self._get("players/squads", {'team': team_id})
            players = risposta[0].get('players', []) if risposta else []
            if not players:
                vuote.append(squadra)
                continue

            for p in players:
                nome_p = p.get('name')
                if not nome_p:
                    continue
                ruolo = {'Goalkeeper': 'P', 'Defender': 'D', 'Attacker': 'A'}.get(
                    p.get('position', 'Midfielder'), 'C')
                if p.get('id'):
                    self.mappa_api_id[normalize_str(nome_p)] = p['id']
                nuovi_giocatori.append({
                    'nome': nome_p, 'ruolo': ruolo, 'squadra': squadra,
                    'api_id': p.get('id'), 'quotazione_base': 1
                })

        if vuote:
            print(f"⚠️ Rosa non scaricata per: {', '.join(vuote)}")
        print(f"✅ Rose sincronizzate: {len(nuovi_giocatori)} giocatori su "
              f"{len(self.serie_a_teams) - len(vuote)} squadre.")
        return nuovi_giocatori

    def associa(self, nome_listone, api_id):
        """
        Collega il nome usato da Fantacalcio ("Martinez L.") all'id API trovato
        durante la scansione rose. Cosi' le statistiche si chiedono per id,
        senza ricerche per nome che sbagliano o vengono rifiutate.
        """
        if nome_listone and api_id:
            self.mappa_api_id[normalize_str(nome_listone)] = api_id

    # ------------------------------------------------------------------
    # STATISTICHE INDIVIDUALI
    # ------------------------------------------------------------------
    def _cerca_id_globale(self, testo_ricerca):
        """
        Trova l'id di un giocatore in QUALSIASI campionato. Serve perche' la
        ricerca dentro la Serie A fallisce sempre per chi arriva dall'estero:
        Mastantuono giocava nella Liga, in Serie A non poteva esserci.
        """
        if len(testo_ricerca) < 4:
            return None
        risposta, stato = self._get("players/profiles", {'search': testo_ricerca}, timeout=8)
        if stato != 'ok' or not risposta:
            return None
        giocatore = risposta[0].get('player', {})
        return giocatore.get('id')


    def _stats_giocatore(self, nome):
        # La chiave include la stagione: un "nessun dato" trovato sul 2024 non
        # deve impedire di riprovare sul 2025 dopo un upgrade di piano.
        chiave = f"{self.season_stats}:{normalize_str(nome)}"
        if chiave in self.cache["stats"]:
            return self.cache["stats"][chiave]

        if not self.api_key or self.quota_esaurita or self.chiamate >= MAX_LOOKUP:
            return None

        nome_normalizzato = normalize_str(nome)
        player_id = self.mappa_api_id.get(nome_normalizzato)

        # L'API accetta solo lettere e spazi: "Martinez L." veniva rifiutato.
        # Si tengono le parole di almeno 3 lettere (via le iniziali puntate).
        parole = [p for p in re.sub(r"[^a-z0-9 ]", " ", nome_normalizzato).split() if len(p) >= 3]
        testo_ricerca = " ".join(parole)

        def costruisci(stagione):
            if player_id:
                return {'id': player_id, 'season': stagione}
            if len(testo_ricerca) >= 4:
                return {'search': testo_ricerca, 'league': LEAGUE_SERIE_A, 'season': stagione}
            return None

        params = costruisci(self.season_stats)
        if params is None:
            return None

        risposta, stato = self._get("players", params, timeout=8)

        # Nessun risultato cercando in Serie A: il giocatore arriva da un altro
        # campionato. Si recupera il suo id globale e si richiede per id.
        if stato == 'ok' and not risposta and not player_id:
            id_trovato = self._cerca_id_globale(testo_ricerca)
            if id_trovato:
                self.mappa_api_id[nome_normalizzato] = id_trovato
                player_id = id_trovato
                risposta, stato = self._get(
                    "players", {'id': player_id, 'season': self.season_stats}, timeout=8)

        # Il piano free non arriva all'ultima stagione: si ripiega su quella prima.
        if stato == 'piano':
            if not self.season_declassata:
                print(f"⚠️ Stagione {self.season_stats} non inclusa nel piano: "
                      f"uso la {self.season_stats - 1} (dati piu' vecchi di un anno).")
                self.season_declassata = True
            self.season_stats -= 1
            risposta, stato = self._get("players", costruisci(self.season_stats), timeout=8)

        if stato != 'ok':
            return None   # errore o quota: NON si mette in cache, si riprova domani

        migliore = None
        for st in (risposta[0].get('statistics', []) if risposta else []):
            apps = st.get('games', {}).get('appearences') or 0
            if apps <= 0:
                continue
            candidato = {
                'presenze': apps,
                'gol': st.get('goals', {}).get('total') or 0,
                'assist': st.get('goals', {}).get('assists') or 0,
                'lega': st.get('league', {}).get('name', ''),
            }
            if migliore is None or candidato['presenze'] > migliore['presenze']:
                migliore = candidato

        # Se la stagione e' stata declassata durante la chiamata, salva su quella usata
        self.cache["stats"][f"{self.season_stats}:{nome_normalizzato}"] = migliore
        return migliore

    def calcola_fantamedia_proiettata(self, nome_giocatore, ruolo):
        dati = self._stats_giocatore(nome_giocatore)
        if not dati or dati['presenze'] <= 0:
            return None
        return self.engine.calcola_pfm_estero(
            presenze=dati['presenze'], gol=dati['gol'], assist=dati['assist'],
            lega=dati['lega'], fascia_squadra_destinazione='Media'
        )

    def verifica_prospetto_giovanile(self, nome_giocatore, squadra):
        dati = self._stats_giocatore(nome_giocatore)
        return bool(dati and dati['presenze'] > 0)


if __name__ == "__main__":
    scout = ScoutEngine()
    scout.carica_squadre_serie_a()
    rose = scout.sincronizza_rose_serie_a()
    print(f"Giocatori totali: {len(rose)} | chiamate usate: {scout.chiamate}")
    scout.salva_cache()
