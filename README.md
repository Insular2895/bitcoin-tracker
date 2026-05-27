<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&height=190&color=gradient&customColorList=12,20,24&text=BTC%20Portfolio%20Tracker&fontAlign=50&fontAlignY=38&fontSize=42&fontColor=ffffff&animation=fadeIn&desc=Local%20DCA%20%2B%20PNL%20%2B%20CSV%20ledger&descAlign=50&descAlignY=62" alt="BTC Portfolio Tracker animated banner">
</p>

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=18&duration=2200&pause=700&color=F7931A&center=true&vCenter=true&width=760&lines=Python+3.11+local+tracker;Binance+read-only+API;Bitcoin+watch-only+wallet;SQLite+local+database;CSV+exports+for+DCA+history" alt="Animated stack badges">
</p>

Tracker local pour suivre ton DCA BTC depuis Binance jusqu'a ton adresse multisig.

Le tracker garde les secrets en local, lit Binance en read-only, suit ton adresse BTC en watch-only, puis sort un tableau lisible et des CSV propres pour l'historique long terme.

## Commande Principale

Depuis ce dossier :

```bash
cd "/Users/insular/Suivis portefeuille BTC"
source .venv/bin/activate
btc-tracker run
```

Menu :

```text
1. Tout lancer : sync Binance + wallet + rapport + CSV
2. Montrer le PNL
3. Montrer les frais
4. Préparer / mettre à jour les CSV
5. Quitter
```

Pour forcer une date de depart :

```bash
btc-tracker run --from-date 2026-05-01
```

Par defaut, le tracker considere que rien n'existe avant le premier jour du mois courant.

## Sortie Lisible

Le rapport terminal reste volontairement simple :

```text
Rapport BTC depuis 2026-05-01

Dépôts EUR réussis    : 3
Montant brut déposé   : 1,002.00 EUR
Frais fiat            : 3.00 EUR
Frais total           : 5.01 EUR
Montant net crédité   : 999.00 EUR
Remboursé net         : 12.00 EUR

Conversions BTC       : 2
Converti en BTC       : 2,000.52 EUR
BTC acheté            : 0.02984907 BTC

BTC envoyé            : 0.01507196 BTC
Frais retrait BTC     : 0.00003000 BTC
Montant BTC entrée    : 0.01493195 BTC
BTC wallet multisig   : 0.01493195 BTC

Valeur actuelle       : 961.81 EUR
Current PNL vs dépôts : -40.19 EUR
```

## CSV

Deux fichiers fixes sont mis a jour a chaque run :

```text
exports/btc_report_latest.csv
exports/btc_ledger_latest.csv
```

Utilisation :

- `btc_report_latest.csv` : resume financier clair.
- `btc_ledger_latest.csv` : detail transaction par transaction pour le DCA.

Le ledger est le fichier important pour dans 1 ou 3 ans : il reste lisible meme avec 100+ transactions, car chaque evenement garde sa ligne.

Colonnes du ledger :

```text
date_utc,event_type,asset,amount,fee,counter_asset,counter_amount,address,txid,status,source,external_id
```

## Ce Qui Est Tracké

Le tracker recupere :

- depots EUR Binance ;
- frais fiat ;
- remboursements fiat ;
- Binance Convert EUR -> BTC ;
- retraits BTC ;
- frais de retrait BTC ;
- montant BTC arrive sur le wallet multisig ;
- valeur actuelle du BTC ;
- PNL courant vs depots EUR.

Le `Frais total` est stable : il ne depend pas du prix actuel du BTC. Il additionne les frais fiat et les frais BTC valorises au cout moyen d'acquisition de la periode.

## Commandes Utiles

Tout lancer sans menu :

```bash
btc-tracker refresh --fiat EUR --from-date 2026-05-01
```

Afficher seulement le rapport sans resynchroniser :

```bash
btc-tracker report --fiat EUR --from-date 2026-05-01
```

Synchroniser Binance :

```bash
btc-tracker sync binance-all --symbols BTCEUR BTCUSDT --days 365
```

Synchroniser les adresses BTC :

```bash
btc-tracker sync wallets
```

Ajouter une adresse watch-only :

```bash
btc-tracker wallet add bc1q... --label "Multisig"
```

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Remplir `.env` :

```bash
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_SYMBOLS=BTCEUR,BTCUSDT
BTC_WATCH_ADDRESSES=<your-btc-address>
```

La cle Binance doit etre read-only uniquement.

Ne mets jamais ta vraie adresse multisig dans `README.md`, `.env.example` ou un CSV committe. Les vraies adresses watch-only restent dans `.env`.

## Securite

- Cle Binance en lecture seule.
- Pas de permission trading.
- Pas de permission retrait.
- `.env` ignore par git.
- `data/` ignore par git.
- `exports/` ignore par git.
- Les adresses et txid sont masques dans les CSV.

## Limites

Ce tracker ne remplace pas un outil fiscal complet.

Binance Convert ne donne pas toujours un frais separe : le spread est integre dans le taux. Les frais explicites sont les frais fiat et les frais de retrait BTC.

Le suivi on-chain confirme ce qui arrive sur l'adresse watch-only, mais ne peut pas deviner seul l'intention fiscale d'une transaction.
