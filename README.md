# DigiFactory Scraper

Scraper robuste pour extraire les données des pages DigiFactory et les stocker dans Supabase.

**Fonctionnalités principales :**
- ✅ **Gating intelligent** : Ne scrape que les pages contenant "Location de véhicule"
- ✅ **Extraction complète** : JSinfos base64, panier jBasketComposer, liens explorer
- ✅ **API FastAPI** : Endpoints REST pour scraping à la demande
- ✅ **Docker ready** : Déploiement simple sur DigitalOcean
- ✅ **Reprise automatique** : SQLite pour suivre la progression

## Architecture

```
digifactory_scraper/
├── src/
│   ├── auth/          # Gestion de session et authentification
│   ├── fetch/         # Client HTTP avec rate limiting
│   ├── parse/         # Parsing HTML et extraction de données
│   │   ├── html_parser.py    # Gating + extraction complète
│   │   ├── jsinfos.py       # Décodage base64 JSinfos
│   │   ├── basket.py        # Extraction panier jBasketComposer
│   │   └── explorer.py      # Extraction liens explorer
│   ├── store/         # Stockage Supabase et gestion d'état
│   ├── jobs/          # Orchestration et métriques
│   └── api/           # API FastAPI
├── data/
│   ├── spool/         # Fichiers JSONL temporaires
│   └── state.db       # Base de données de progression
└── main.py            # Point d'entrée CLI
```

## Installation

### Prérequis

- Python 3.11+
- Compte Supabase configuré
- Accès DigiFactory avec identifiants ou cookie de session

### Setup

1. Cloner le projet et installer les dépendances :

```bash
pip install -e .
```

2. Configurer les variables d'environnement :

```bash
# Option 1: Copier le fichier d'exemple
cp env.example.txt .env
# Éditer .env avec vos credentials

# Option 2: Utiliser le script helper
bash setup_env.sh
# Puis éditer .env avec vos credentials
```

3. Créer la table Supabase :

Exécuter le DDL fourni dans `supabase_schema.sql` dans votre projet Supabase.

## Quickstart DEV

### Tester rapidement sans risque

```bash
# Installer
pip install -r requirements.txt

# IMPORTANT: Si le login automatique ne fonctionne pas, utilisez un cookie manuel
# Voir TROUBLESHOOTING.md pour extraire le cookie depuis votre navigateur

# Tester un seul nr (dry-run, pas d'écriture Supabase)
make dev
# ou
python -m src.main --nr 52000 --dev --dry-run

# Avec cookie manuel (recommandé si login échoue)
python -m src.main --nr 52000 --dev --dry-run --cookie-only

# Tester une petite plage
python -m src.main --start 52000 --end 52010 --dev

# Tester avec écriture Supabase (explicite)
python -m src.main --nr 52000 --dev --write-supabase
```

**Résultats dans `data/dev/52000/` :**
- `summary.json` : Résumé (gate, URLs, compteurs)
- `extracted.json` : Données complètes qui iraient en Supabase
- `pages/view.html.gz` : HTML compressé (si `--store-html`)

### Vérifier sans écrire en base

Le mode `--dev --dry-run` :
- ✅ Ne touche **jamais** à Supabase
- ✅ Stocke tout dans `data/dev/`
- ✅ Logs verbeux pour inspection
- ✅ Paramètres safe (concurrency=2, rate=0.5 req/s)

## Utilisation

### Mode DEV (développement/test)

**Objectif** : Tester vite sans risquer d'écrire en prod.

```bash
# Un seul nr
python -m src.main --nr 52000 --dev --dry-run

# Petite plage
python -m src.main --start 52000 --end 52005 --dev

# Avec écriture Supabase (explicite)
python -m src.main --nr 52000 --dev --write-supabase
```

**Paramètres DEV par défaut :**
- `concurrency=2` (vs 20 en PROD)
- `rate_per_domain=0.5` (1 req toutes les 2 sec)
- `batch_size=10` (vs 1000 en PROD)
- Logs verbeux (DEBUG level)

**Sécurité DEV :**
- `--dev` sans `--write-supabase` → **interdiction d'écrire** dans Supabase
- Même si les credentials sont présents, le mode DEV bloque l'écriture
- Utiliser `--write-supabase` explicitement pour forcer l'écriture

**Outputs DEV :**
- `data/dev/{nr}/summary.json` : Résumé avec gate, URLs, compteurs
- `data/dev/{nr}/extracted.json` : Données complètes
- `data/dev/{nr}/pages/*.html.gz` : HTML compressé (si `--store-html`)

### Mode PROD (production)

**Objectif** : Run long, stable, avec reprise.

```bash
# Scraping complet
python -m src.main --start 1 --end 58000 --concurrency 20

# Reprise après interruption (activé par défaut en PROD)
python -m src.main --start 1 --end 58000 --resume
```

**Paramètres PROD :**
- `concurrency=20` (configurable)
- `rate_per_domain=2` (req/sec)
- `batch_size=1000`
- `resume=true` par défaut

### Options CLI

**Range :**
- `--nr N` : Scraper un seul nr
- `--start N --end M` : Plage de nr

**Mode :**
- `--dev` : Mode développement (safe defaults)
- `--dry-run` : Aucune écriture Supabase
- `--write-supabase` : Override explicite pour écrire en DEV

**Run Control (anti-boucles) :**
- `--limit-gated N` : Stop après N ventes qui passent le gate
- `--stop-after-minutes M` : Stop propre après M minutes
- `--max-errors N` : Stop si erreurs totales > N
- `--max-consecutive-errors N` : Stop si N erreurs d'affilée
- `--max-403 N` : Stop si 403 errors > N
- `--max-429 N` : Stop si 429 errors > N
- `--fail-fast` : Stop dès la première erreur critique (auth)

**Auth modes :**
- `--cookie-only` : Utilise uniquement SESSION_COOKIE, ne tente jamais login
- `--login-only` : Ignore cookie, fait login avec USERNAME/PASSWORD

**Storage :**
- `--store-html` : Stocker HTML compressé (DEV mode, max 1.5MB par défaut)
- `--max-html-bytes N` : Limite taille HTML avant skip (default: 1.5MB)
- `--no-store-jsinfos` : Ne pas stocker JSinfos (default: store)
- `--no-store-explorer` : Ne pas stocker explorer links (default: store si gate passe)
- `--explorer-max-links K` : Maximum liens explorer par page (default: 200)
- `--explorer-store on/off` : Activer/désactiver stockage explorer (default: on)

**Performance :**
- `--concurrency N` : Nombre de requêtes concurrentes
- `--batch-size N` : Taille des batches pour Supabase
- `--resume` : Reprendre depuis le dernier checkpoint

### Mode API (scraping à la demande)

#### Démarrer l'API

```bash
# Local
uvicorn src.api.main:app --reload

# Ou avec Docker
docker-compose up
```

#### Endpoints disponibles

- `GET /health` : Health check
- `POST /scrape` : Scraper un nr
  ```json
  {
    "nr": 52000
  }
  ```
- `GET /scrape/{nr}` : Scraper un nr (GET version)

#### Exemple d'utilisation

```bash
# Scraper un nr
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"nr": 52000}'

# Health check
curl http://localhost:8000/health
```

### Règle de gating

Le scraper applique une **règle de gating** :

1. **Vérification initiale** : Fetch de `/digi/com/cto/view?nr=XXXX`
2. **Détection** : Recherche de "Location de véhicule" dans le HTML
3. **Si absent** : Enregistrement minimal (gate_passed=false) et arrêt
4. **Si présent** : Extraction complète des 5 pages :
   - `/digi/com/cto/view?nr=XXXX`
   - `/digi/com/cto/viewPayment?nr=XXXX`
   - `/digi/com/cto/viewLogistic?nr=XXXX`
   - `/digi/com/cto/viewInfos?nr=XXXX`
   - `/digi/com/cto/viewOrders?nr=XXXX`

### Extraction complète (quand gate passe)

- **JSinfos base64** : Décodage et parsing JSON (gmKey masqué)
- **Panier** : Extraction lignes depuis `jBasketComposer()`
- **Explorer links** : Tous les liens `<a href>` et attributs `jsinfos="url:'...'"`
- **Données Location** : Véhicule, semaine, boutons (Contrat initial, Dernière vente)

## Configuration

### Variables d'environnement

- `BASE_URL` : URL de base DigiFactory
- `USERNAME` / `PASSWORD` : Identifiants (Option A)
- `SESSION_COOKIE` : Cookie de session (Option B, fallback)
- `CONCURRENCY` : Concurrence HTTP (10-30 recommandé)
- `RATE_PER_DOMAIN` : Requêtes par seconde par domaine (2 recommandé)
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE` : Configuration Supabase

### Stratégies de robustesse

- **Détection d'expiration de session** : Relogin automatique si redirection vers login
- **Retries avec backoff** : Gestion des timeouts et erreurs 5xx
- **Spool disque** : Sauvegarde JSONL si Supabase est indisponible
- **Idempotence** : Upsert par `nr` permet relancement sans doublons
- **State tracking** : SQLite pour suivre la progression

## Tests

### Lancer les tests

```bash
# Tous les tests
make test
# ou
pytest tests/ -v

# Tests spécifiques
make test-gating
make test-jsinfos
make test-basket
```

### Tests disponibles

- `test_gating.py` : Tests de détection "Location de véhicule"
- `test_jsinfos.py` : Tests de décodage base64 et masquage gmKey
- `test_basket.py` : Tests d'extraction panier jBasketComposer
- `test_redact.py` : Tests de redaction des secrets

## Docker local pour test

### Tester dans Docker avant déploiement

```bash
# Mode DEV dans Docker
docker-compose -f docker-compose.dev.yml up --build

# Ou avec profile
docker-compose --profile dev up
```

Le container monte `./data` en volume pour voir les fichiers générés.

## Déploiement sur DigitalOcean

### Option 1 : Docker Compose sur Droplet (recommandé)

#### Sur un Droplet Ubuntu

1. **Installer Docker et Docker Compose** :
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
sudo apt-get install docker-compose-plugin
```

2. **Cloner et configurer** :
```bash
git clone <repo>
cd digifactory_scraper
cp env.example.txt .env
# Éditer .env avec vos credentials
```

3. **Démarrer en PROD** :
```bash
docker-compose -f docker-compose.prod.yml up -d
```

4. **Vérifier** :
```bash
# Logs
docker-compose -f docker-compose.prod.yml logs -f

# Health check
curl http://localhost:8000/health

# Vérifier que ça scrape sans écrire (test)
docker-compose -f docker-compose.prod.yml exec scraper-api \
  python -m src.main --nr 52000 --dev --dry-run
```

**Persistance :**
- `./data:/app/data` monté en volume
- `state.db` pour la reprise
- `spool/` pour les données en attente

#### Reverse proxy avec Caddy (HTTPS)

1. **Configurer Caddyfile** :
```bash
# Éditer Caddyfile avec votre domaine
nano Caddyfile
```

2. **Redémarrer** :
```bash
docker-compose -f docker-compose.prod.yml restart caddy
```

### Option 2 : DigitalOcean App Platform

1. **Connecter GitHub** à votre projet
2. **Configurer le build** :
   - Build command: `pip install -r requirements.txt`
   - Run command: `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
3. **Ajouter les variables d'environnement** dans l'interface App Platform

### Option 3 : Systemd (CLI mode)

Créer `/etc/systemd/system/digifactory-scraper.service` :

```ini
[Unit]
Description=DigiFactory Scraper
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/digifactory_scraper
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python -m src.main --start 1 --end 58000 --resume
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Variables d'environnement

Stocker les secrets dans `.env` ou variables d'environnement système :

```bash
BASE_URL=https://entrepreneur.digifactory.fr
SESSION_COOKIE=DigifactoryBO=...
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE=...
```

### Firewall

```bash
# Autoriser uniquement les connexions sortantes nécessaires
ufw allow out 443/tcp  # HTTPS
ufw allow out 80/tcp   # HTTP (si nécessaire)
ufw allow 8000/tcp     # API (si exposée)
```

## Ops DigitalOcean (maintenance)

### Commandes de maintenance

```bash
# Mise à jour
git pull
docker compose -f docker-compose.prod.yml up -d --build

# Logs
docker compose -f docker-compose.prod.yml logs -f --tail=200

# Restart
docker compose -f docker-compose.prod.yml restart scraper-api

# Cleanup spool (fichiers > 7 jours)
python -m src.store.spool_cleanup --older-than-days 7

# Cleanup spool (dry-run)
python -m src.store.spool_cleanup --dry-run

# Ou via Makefile
make cleanup-spool
```

### Vérifier que ça marche

```bash
# Test sans écrire
docker compose -f docker-compose.prod.yml exec scraper-api \
  python -m src.main --nr 52000 --dev --dry-run

# Vérifier métriques
cat data/metrics.jsonl | tail -5

# Vérifier health API
curl http://localhost:8000/health
```

## Sécurité API

Si l'API FastAPI est accessible hors localhost :

**Option 1 : API Key (recommandé)**
```bash
# Dans .env
API_KEY=your-secret-key

# Utilisation
curl -H "X-API-KEY: your-secret-key" http://localhost:8000/scrape/52000
```

**Option 2 : Binder sur localhost uniquement**
```bash
# Dans docker-compose.prod.yml
command: uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Par défaut, l'API écoute sur `0.0.0.0` (tous les interfaces). Configurez le firewall ou utilisez un reverse proxy avec authentification.

## Métriques

Le scraper affiche en temps réel :
- Requêtes/seconde
- Pages réussies/échouées
- ETA estimée
- Progression (nr traité / total)

## Notes de sécurité

- **Ne jamais** commiter `.env` ou `data/`
- **Ne jamais** logger les cookies de session
- Utiliser `SUPABASE_SERVICE_ROLE` uniquement côté serveur
- Configurer le firewall pour limiter les connexions sortantes

## Troubleshooting

### Session expirée / Login échoue

**Si le login automatique échoue** (message "No session cookie found") :

1. **Utiliser un cookie manuel** (recommandé) :
   - Extraire le cookie `DigifactoryBO` depuis votre navigateur (F12 → Application → Cookies)
   - Ajouter dans `.env` : `SESSION_COOKIE=DigifactoryBO=votre_valeur`
   - Utiliser `--cookie-only` : `python -m src.main --nr 52000 --dev --dry-run --cookie-only`

2. **Vérifier les credentials** : `USERNAME`/`PASSWORD` doivent être corrects

3. **Vérifier l'URL de login** : `LOGIN_URL` doit pointer vers la bonne page

Voir `TROUBLESHOOTING.md` pour plus de détails.

### Supabase timeout

Les données sont automatiquement spoolées sur disque (`data/spool/`). Relancer le scraper pour reprendre l'upload.

### Rate limiting

Réduire `CONCURRENCY` et `RATE_PER_DOMAIN` si vous recevez des 429.

## Comment vérifier que ça marche sans écrire en base

### Méthode 1 : Mode DEV + Dry-run

```bash
# Tester un nr
python -m src.main --nr 52000 --dev --dry-run

# Vérifier les outputs
cat data/dev/52000/summary.json
cat data/dev/52000/extracted.json
ls -lh data/dev/52000/pages/
```

### Méthode 2 : Vérifier les logs

Les logs DEV affichent :
```
[DEV] nr 52000: Gate PASSED (Location de véhicule)
[DEV] nr 52000: Crawling 5 URLs: ['view', 'payment', 'logistic', 'infos', 'orders']
[DEV] nr 52000: Extraction complete - JSinfos: 3, Basket lines: 5, Explorer links: 12, Time: 2.34s
```

### Méthode 3 : Tester les endpoints API

```bash
# Health check
curl http://localhost:8000/health

# Scraper un nr (sauvegarde en background)
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"nr": 52000}'
```

## Performance

- **Estimation** : ~290k requêtes (58k nr × 5 pages)
- **Avec gating** : Réduction significative si beaucoup de nr ne passent pas le gate
- **Mode DEV** : ~5-10 req/min (safe pour tests)
- **Mode PROD** : ~2 req/sec × concurrency (configurable)
- **Avec 2 req/sec** : ~40h (peut être réduit avec plus de concurrence)
- **Priorité** : Stabilité et reprise > vitesse

## Structure des données extraites

### Quand gate_passed = false
```json
{
  "nr": 12345,
  "gate_passed": false,
  "reason": "Location de véhicule not found"
}
```

### Quand gate_passed = true
```json
{
  "nr": 52000,
  "gate_passed": true,
  "pages": {
    "view": {
      "url": "...",
      "status_code": 200,
      "hash": "...",
      "jsinfos": {...},
      "basket_lines": [...],
      "explorer_links": [...],
      "vehicule": "...",
      "semaine": "2025-43",
      "button_links": [...]
    },
    "payment": {...},
    "logistic": {...},
    "infos": {...},
    "orders": {...}
  },
  "jsinfos": {...},
  "explorer_links": [...]
}
```

