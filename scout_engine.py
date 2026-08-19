"""
scout_engine.py - Tutto cio' che passa da API-Football.

Regola che vale ovunque qui dentro: si registrano FATTI (presenze, minuti,
gare saltate, causa dichiarata). Non si deduce mai il PERCHE'.
"""

import os
import re
import time
import json
import datetime

import requests

from fanta_engine import FantaEngine
from testo import normalize_str

LEAGUE_SERIE_A = 135
LEAGUE_SERIE_B = 136

# Stagione appena conclusa (2025 = 2025/26): e' quella da cui si proietta l'asta.
SEASON_STATS = int(os.getenv("FANTA_SEASON_STATS", "2025"))
SEASON_CORRENTE = int(os.getenv("FANTA_SEASON", "2026"))

# Tetto ai SOLI lookup per giocatore. Prima il confronto era con il contatore
# globale delle chiamate: rose (20) + storico infortuni (20) lo saturavano
# prima ancora di arrivare alle proiezioni, che quindi non partivano quasi mai.
MAX_LOOKUP = int(os.getenv("FANTA_MAX_LOOKUP", "600"))
# Quota separata per l'avviso "giocatori fuori dal listone": e' un extra,
# non deve mangiarsi il budget delle proiezioni.
MAX_LOOKUP_AVVISO = int(os.getenv("FANTA_MAX_LOOKUP_AVVISO", "60"))

# Piano free: ~10 chiamate/minuto -> 6.5. Piano Pro: 300/minuto -> 0.3.
PAUSA_CHIAMATE = float(os.getenv("FANTA_PAUSA", "0.3"))
ATTESA_DOPO_429 = float(os.getenv("FANTA_ATTESA_429", "60"))
MAX_429_CONSECUTIVI = 3

CACHE_FILE = "scout_cache.json"
# Cambiare questo numero invalida le statistiche in cache. Va alzato ogni volta
# che cambia il MODO in cui i dati vengono calcolati, altrimenti i valori
# sbagliati salvati ieri sopravvivono alla correzione di oggi.
CACHE_VERSIONE = 3

# Limiti fisici di UNA stagione: 38 di campionato + coppe + Europa + nazionale.
# Oltre, il dato e' quasi certamente la somma di piu' annate o di un omonimo.
MAX_PRESENZE_STAGIONE = int(os.getenv("FANTA_MAX_PRESENZE", "70"))
MAX_MINUTI_STAGIONE = MAX_PRESENZE_STAGIONE * 95

# Assenze che NON sono un problema fisico. Tutto il resto viene contato come
# infortunio: meglio sovrastimare il rischio fisico che nasconderlo.
MOTIVI_NON_FISICI = (
    'suspend', 'red card', 'yellow card', 'card suspension', 'ban',
    'national', 'international duty', 'personal reasons', 'rest', 'rested',
    'inactive', 'coach', 'not in squad', 'squad rotation', 'other',
    'doping', 'contract', 'transfer', 'visa',
)

TEAM_ID_NOTI = {
    'inter': 505, 'milan': 489, 'juventus': 496, 'napoli': 492,
    'roma': 497, 'atalanta': 499, 'lazio': 487, 'fiorentina': 502,
    'bologna': 500, 'torino': 503, 'udinese': 494, 'genoa': 495,
    'verona': 504, 'cagliari': 490, 'lecce': 867, 'como': 1020,
    'parma': 523, 'sassuolo': 488, 'monza': 1579, 'venezia': 517,
    'frosinone': 512, 'cremonese': 520, 'pisa': 522, 'empoli': 511,
    'salernitana': 514, 'spezia': 515,
}

ALIAS_SQUADRE = {
    'hellas verona': 'Verona', 'ac milan': 'Milan', 'as roma': 'Roma',
    'ssc napoli': 'Napoli', 'fc internazionale': 'Inter', 'inter': 'Inter',
    'us lecce': 'Lecce', 'us cremonese': 'Cremonese', 'ac pisa': 'Pisa',
    'us sassuolo': 'Sassuolo', 'sassuolo': 'Sassuolo', 'pisa': 'Pisa',
    'cremonese': 'Cremonese', 'ac monza': 'Monza', 'venezia fc': 'Venezia',
    'frosinone calcio': 'Frosinone', 'juventus': 'Juventus',
}


def nome_squadra_listone(nome_api):
    return ALIAS_SQUADRE.get(normalize_str(nome_api), str(nome_api).strip())


def motivo_e_fisico(motivo):
    """True se l'assenza dichiarata e' di natura fisica."""
    testo = str(motivo or "").lower()
    if not testo:
        return True
    return not any(chiave in testo for chiave in MOTIVI_NON_FISICI)


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
        self.foto_per_id = {}

        self.chiamate = 0          # tutte le chiamate HTTP del run
        self.lookup = 0            # solo le ricerche statistiche per giocatore
        self.lookup_avviso = 0

        self.season_stats = SEASON_STATS
        self.season_declassata = False
        self.quota_esaurita = False
        self.errori_429 = 0
        self.anomalie = []         # dati scartati perche' fuori scala
        self._ultima_chiamata = 0.0

        self.cache = self._carica_cache()

    # ------------------------------------------------------------------
    # CACHE
    # ------------------------------------------------------------------
    def _carica_cache(self):
        vuota = {"versione": CACHE_VERSIONE, "stats": {}, "team_ids": {}, "infortuni": {}}
        if not os.path.exists(CACHE_FILE):
            return vuota
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                dati = json.load(f)
        except Exception:
            return vuota

        if int(dati.get("versione", 0)) != CACHE_VERSIONE:
            print(f"♻️  Cache di versione vecchia: statistiche e storico infortuni "
                  f"ricalcolati da zero (gli Id squadra restano).")
            return {
                "versione": CACHE_VERSIONE,
                "stats": {},
                "team_ids": dati.get("team_ids", {}),
                "infortuni": dati.get("infortuni", {}),
            }

        dati.setdefault("stats", {})
        dati.setdefault("team_ids", {})
        dati.setdefault("infortuni", {})
        return dati

    def salva_cache(self):
        self.cache["versione"] = CACHE_VERSIONE
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

        for _ in range(MAX_429_CONSECUTIVI):
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
                    timeout=timeout,
                )
            except Exception as e:
                print(f"⚠️ Errore rete su /{endpoint}: {e}")
                return [], 'errore'

            if res.status_code == 429:
                self.errori_429 += 1
                print(f"⏳ HTTP 429 su /{endpoint}: attendo {ATTESA_DOPO_429:.0f}s.")
                time.sleep(ATTESA_DOPO_429)
                continue

            if res.status_code != 200:
                print(f"⚠️ /{endpoint}: HTTP {res.status_code}")
                return [], 'errore'

            try:
                data = res.json()
            except Exception:
                return [], 'errore'

            errori = data.get('errors')
            if errori and not isinstance(errori, list):
                testo = " ".join(str(v) for v in errori.values()).lower()
                if 'request limit' in testo or 'requests' in errori:
                    if not self.quota_esaurita:
                        print("🛑 Quota API esaurita: il resto si calcola dai dati locali.")
                    self.quota_esaurita = True
                    return [], 'quota'
                if 'plan' in errori:
                    print(f"⚠️ /{endpoint} non incluso nel piano: {errori.get('plan')}")
                    return [], 'piano'
                print(f"⚠️ /{endpoint} errore API: {errori}")
                return [], 'errore'

            self.errori_429 = 0
            return data.get('response', []) or [], 'ok'

        print("🛑 HTTP 429 ripetuti: limite di frequenza non gestibile, interrompo.")
        self.quota_esaurita = True
        return [], 'quota'

    # ------------------------------------------------------------------
    # ID SQUADRE
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

        if da_risolvere:
            print(f"🔎 Risoluzione Id per: {', '.join(da_risolvere)}")
            trovati = {}
            for lega in (LEAGUE_SERIE_A, LEAGUE_SERIE_B):
                risposta, stato = self._get("teams", {'league': lega, 'season': self.season_stats})
                if stato == 'piano':
                    risposta, stato = self._get(
                        "teams", {'league': lega, 'season': self.season_stats - 1})
                if stato != 'ok':
                    continue
                for item in risposta:
                    team = item.get('team', {})
                    if team.get('id') and team.get('name'):
                        chiave = normalize_str(nome_squadra_listone(team['name']))
                        trovati[chiave] = team['id']

            for nome in list(da_risolvere):
                tid = trovati.get(normalize_str(nome))
                if tid:
                    squadre[nome] = tid
                    self.cache["team_ids"][normalize_str(nome)] = tid
                    da_risolvere.remove(nome)

        if da_risolvere:
            print(f"⚠️ Id non risolti (rose non scaricabili): {', '.join(da_risolvere)}")

        self.serie_a_teams = squadre
        print(f"✅ Squadre {SEASON_CORRENTE}/{str(SEASON_CORRENTE + 1)[-2:]}: "
              f"{len(squadre)} su {len(nomi_squadre)} con Id valido.")
        return squadre

    # ------------------------------------------------------------------
    # ROSE
    # ------------------------------------------------------------------
    def sincronizza_rose_serie_a(self):
        if not self.api_key:
            print("⚠️ API Key non trovata. Sincronizzazione rose saltata.")
            return []
        if not self.serie_a_teams:
            self.carica_squadre_serie_a()

        giocatori, vuote = [], []
        print("📡 Scansione rose in corso...")
        for squadra, team_id in self.serie_a_teams.items():
            if self.quota_esaurita:
                vuote.append(squadra)
                continue

            risposta, _ = self._get("players/squads", {'team': team_id})
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
                    if p.get('photo'):
                        self.foto_per_id[p['id']] = p['photo']
                giocatori.append({
                    'nome': nome_p, 'ruolo': ruolo, 'squadra': squadra,
                    'api_id': p.get('id'),
                })

        if vuote:
            print(f"⚠️ Rosa non scaricata per: {', '.join(vuote)}")
        print(f"✅ Rose sincronizzate: {len(giocatori)} giocatori su "
              f"{len(self.serie_a_teams) - len(vuote)} squadre.")
        return giocatori

    def associa(self, nome_listone, api_id):
        """Collega il nome del listone all'id API: le statistiche si chiedono
        per id, senza ricerche per nome che sbagliano persona."""
        if nome_listone and api_id:
            self.mappa_api_id[normalize_str(nome_listone)] = api_id

    # ------------------------------------------------------------------
    # STATISTICHE INDIVIDUALI
    # ------------------------------------------------------------------
    def _cerca_id_globale(self, testo_ricerca):
        """Id di un giocatore in QUALSIASI campionato: serve per chi arriva
        dall'estero e in Serie A non puo' esistere."""
        if len(testo_ricerca) < 4:
            return None
        risposta, stato = self._get("players/profiles", {'search': testo_ricerca}, timeout=8)
        if stato != 'ok' or not risposta:
            return None
        return risposta[0].get('player', {}).get('id')

    def _budget_lookup_esaurito(self, avviso=False):
        if avviso:
            return self.lookup_avviso >= MAX_LOOKUP_AVVISO
        return self.lookup >= MAX_LOOKUP

    def _stats_giocatore(self, nome, avviso=False):
        chiave = f"{self.season_stats}:{normalize_str(nome)}"
        if chiave in self.cache["stats"]:
            memorizzato = self.cache["stats"][chiave]
            # I "senza dati" vengono ricordati: senza questo ogni notte si
            # ripetevano centinaia di ricerche destinate a non trovare nulla.
            return None if memorizzato == "vuoto" else memorizzato

        if not self.api_key or self.quota_esaurita or self._budget_lookup_esaurito(avviso):
            return None

        nome_norm = normalize_str(nome)
        player_id = self.mappa_api_id.get(nome_norm)

        # L'API accetta solo lettere e spazi: "Martinez L." viene rifiutato.
        parole = [p for p in re.sub(r"[^a-z0-9 ]", " ", nome_norm).split() if len(p) >= 3]
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

        if avviso:
            self.lookup_avviso += 1
        else:
            self.lookup += 1

        risposta, stato = self._get("players", params, timeout=8)

        if stato == 'ok' and not risposta and not player_id:
            id_trovato = self._cerca_id_globale(testo_ricerca)
            if id_trovato:
                self.mappa_api_id[nome_norm] = id_trovato
                player_id = id_trovato
                risposta, stato = self._get(
                    "players", {'id': player_id, 'season': self.season_stats}, timeout=8)

        if stato == 'piano':
            if not self.season_declassata:
                print(f"⚠️ Stagione {self.season_stats} non inclusa nel piano: "
                      f"uso la {self.season_stats - 1} (dati piu' vecchi di un anno).")
                self.season_declassata = True
            self.season_stats -= 1
            risposta, stato = self._get("players", costruisci(self.season_stats), timeout=8)

        if stato != 'ok':
            return None      # errore o quota: NON si mette in cache, si riprova domani

        record = self._estrai_stagione(risposta, nome)
        chiave = f"{self.season_stats}:{nome_norm}"
        self.cache["stats"][chiave] = record if record else "vuoto"
        return record

    def _estrai_stagione(self, risposta, nome):
        """Somma le voci della SOLA stagione richiesta, con i tetti di sicurezza."""
        migliore = None
        presenze_tot, titolari_tot, minuti_tot = 0, 0, 0
        squadre, campionati = set(), set()

        for st in (risposta[0].get('statistics', []) if risposta else []):
            games = st.get('games', {}) or {}
            apps = games.get('appearences') or 0
            if apps <= 0:
                continue

            lega_info = st.get('league', {}) or {}

            # Filtro stagione: la ricerca per nome restituisce piu' annate.
            # Se la stagione non e' dichiarata la voce si SCARTA: prima veniva
            # tenuta, ed e' cosi' che spuntavano 69 presenze e 5277 minuti.
            stagione_voce = lega_info.get('season')
            if stagione_voce is None or int(stagione_voce) != int(self.season_stats):
                continue

            # Le competizioni per nazionali hanno country "World": incluse,
            # la Turchia diventava una "seconda squadra" del giocatore.
            if str(lega_info.get('country', '')).strip().lower() == 'world':
                continue

            presenze_tot += apps
            titolari_tot += games.get('lineups') or 0
            minuti_tot += games.get('minutes') or 0

            squadra = (st.get('team', {}) or {}).get('name', '')
            if squadra:
                squadre.add(squadra)
            lega = lega_info.get('name', '')
            if lega:
                campionati.add(lega)

            candidato = {
                'presenze': apps,
                'gol': (st.get('goals', {}) or {}).get('total') or 0,
                'assist': (st.get('goals', {}) or {}).get('assists') or 0,
                'lega': lega,
            }
            if migliore is None or candidato['presenze'] > migliore['presenze']:
                migliore = candidato

        if migliore is None:
            return None

        # Tetto di sicurezza: oltre questi numeri il dato non e' di una stagione
        # sola (o e' di un omonimo). Meglio nessun dato che un dato falso.
        if presenze_tot > MAX_PRESENZE_STAGIONE or minuti_tot > MAX_MINUTI_STAGIONE:
            self.anomalie.append(f"{nome}: {presenze_tot} pres / {minuti_tot} min scartati")
            presenze_tot = min(presenze_tot, migliore['presenze'])
            titolari_tot, minuti_tot = 0, 0
            squadre = {list(squadre)[0]} if squadre else set()

        migliore['presenze_totali'] = presenze_tot
        migliore['squadre_stagione'] = max(1, len(squadre))
        migliore['campionati'] = sorted(campionati)
        migliore['da_titolare'] = titolari_tot
        migliore['minuti'] = minuti_tot
        return migliore

    def calcola_fantamedia_proiettata(self, nome_giocatore, ruolo):
        dati = self._stats_giocatore(nome_giocatore)
        if not dati or dati['presenze'] <= 0:
            return None
        return self.engine.calcola_pfm_estero(
            presenze=dati['presenze'], gol=dati['gol'], assist=dati['assist'],
            lega=dati['lega'], fascia_squadra_destinazione='Media')

    def presenze_stagione(self, nome_giocatore):
        dati = self._stats_giocatore(nome_giocatore)
        if not dati:
            return None
        return {
            'totali': dati.get('presenze_totali', dati.get('presenze', 0)),
            'squadre': dati.get('squadre_stagione', 1),
            'da_titolare': dati.get('da_titolare', 0),
            'minuti': dati.get('minuti', 0),
        }

    def ha_esperienza(self, nome_giocatore):
        """
        Ha gia' giocato da professionista? Si risponde SOLO con quello che e'
        gia' in cache: non vale una chiamata API in piu' per ogni giocatore da
        1 credito. (Prima si chiamava verifica_prospetto_giovanile e prometteva
        un giudizio sull'eta' che non ha mai calcolato.)
        """
        chiave = f"{self.season_stats}:{normalize_str(nome_giocatore)}"
        dati = self.cache["stats"].get(chiave)
        if not dati or dati == "vuoto":
            return False
        return dati.get('presenze', 0) > 0

    # ------------------------------------------------------------------
    # INFORTUNI
    # ------------------------------------------------------------------
    def infortuni_correnti(self):
        """Chi e' fermo adesso. {id_api: {'tipo','motivo','squadra','nome_api'}}"""
        oggi = datetime.date.today().isoformat()
        risposta, stato = self._get(
            "injuries", {'league': LEAGUE_SERIE_A, 'season': SEASON_CORRENTE, 'date': oggi})
        if stato != 'ok' or not risposta:
            risposta, stato = self._get(
                "injuries", {'league': LEAGUE_SERIE_A, 'season': SEASON_CORRENTE})
        if stato != 'ok':
            print("⚠️ Elenco infortuni non disponibile.")
            return {}

        fermi = {}
        for voce in risposta:
            giocatore = voce.get('player', {}) or {}
            id_api = giocatore.get('id')
            if not id_api:
                continue
            fermi[id_api] = {
                'tipo': giocatore.get('type') or 'Indisponibile',
                'motivo': giocatore.get('reason') or '',
                'squadra': (voce.get('team', {}) or {}).get('name', ''),
                'nome_api': giocatore.get('name', ''),
            }
        print(f"🚑 Indisponibili rilevati: {len(fermi)}")
        return fermi

    def storico_infortuni(self, season=None):
        """
        Gare saltate nella stagione indicata, divise per natura dell'assenza.

        {id_api: {'gare_fisiche', 'gare_altro', 'motivo', 'motivo_altro'}}

        La divisione e' il punto: prima squalifiche, nazionale e turnover
        finivano nello stesso contatore degli infortuni, e un difensore con 4
        giornate di squalifica risultava "fragile".
        """
        season = season or self.season_stats
        if not self.serie_a_teams:
            return {}

        cache_key = f"infortuni_stagione_{season}"
        if cache_key in self.cache:
            return {int(k): v for k, v in self.cache[cache_key].items()}

        storico = {}
        for _, team_id in self.serie_a_teams.items():
            if self.quota_esaurita:
                break
            risposta, stato = self._get("injuries", {'team': team_id, 'season': season})
            if stato != 'ok':
                continue

            for voce in risposta:
                giocatore = voce.get('player', {}) or {}
                id_api = giocatore.get('id')
                if not id_api:
                    continue
                motivo = giocatore.get('reason') or giocatore.get('type') or 'Infortunio'
                record = storico.setdefault(
                    id_api, {'gare_fisiche': 0, 'gare_altro': 0,
                             '_mot_fis': {}, '_mot_alt': {}})
                if motivo_e_fisico(motivo):
                    record['gare_fisiche'] += 1
                    record['_mot_fis'][motivo] = record['_mot_fis'].get(motivo, 0) + 1
                else:
                    record['gare_altro'] += 1
                    record['_mot_alt'][motivo] = record['_mot_alt'].get(motivo, 0) + 1

        for record in storico.values():
            fis, alt = record.pop('_mot_fis'), record.pop('_mot_alt')
            record['motivo'] = max(fis, key=fis.get) if fis else ''
            record['motivo_altro'] = max(alt, key=alt.get) if alt else ''

        if storico:
            self.cache[cache_key] = {str(k): v for k, v in storico.items()}
        print(f"🏥 Storico {season}: {len(storico)} giocatori con gare saltate.")
        return storico


if __name__ == "__main__":
    scout = ScoutEngine()
    scout.carica_squadre_serie_a(list(TEAM_ID_NOTI))
    rose = scout.sincronizza_rose_serie_a()
    print(f"Giocatori totali: {len(rose)} | chiamate: {scout.chiamate}")
    scout.salva_cache()
