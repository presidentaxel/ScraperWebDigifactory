# Changelog - Mode DEV et améliorations

## Nouvelles fonctionnalités

### 1. Mode DEV (développement/test)

**Commande simple :**
```bash
make dev
# ou
python -m src.main --nr 52000 --dev --dry-run
```

**Caractéristiques :**
- ✅ Paramètres safe par défaut (concurrency=2, rate=0.5 req/s)
- ✅ Logs verbeux avec détails par nr
- ✅ Stockage local dans `data/dev/{nr}/`
- ✅ Protection : pas d'écriture Supabase sauf `--write-supabase` explicite

### 2. Flags CLI ajoutés

- `--nr N` : Scraper un seul nr
- `--dev` : Mode développement
- `--dry-run` : Aucune écriture Supabase
- `--write-supabase` : Override pour écrire en DEV
- `--store-html` : Stocker HTML compressé
- `--no-store-jsinfos` : Ne pas stocker JSinfos
- `--no-store-explorer` : Ne pas stocker explorer links

### 3. Outputs DEV

Structure dans `data/dev/{nr}/` :
- `summary.json` : Résumé (gate, URLs, compteurs)
- `extracted.json` : Données complètes
- `pages/*.html.gz` : HTML compressé (si `--store-html`)

### 4. Tests

Tests pytest ajoutés :
- `tests/test_gating.py` : Détection "Location de véhicule"
- `tests/test_jsinfos.py` : Décodage base64 et masquage gmKey
- `tests/test_basket.py` : Extraction panier

Lancer : `make test` ou `pytest tests/ -v`

### 5. Docker DEV

`docker-compose.dev.yml` pour tester dans Docker :
```bash
docker-compose -f docker-compose.dev.yml up --build
```

### 6. Makefile

Commandes utiles :
- `make dev` : Test rapide un nr
- `make dev-range` : Test petite plage
- `make test` : Lancer les tests
- `make docker-dev` : Docker en mode DEV

## Sécurité DEV

**Règle critique :**
- En mode `--dev` sans `--write-supabase` → **interdiction absolue** d'écrire dans Supabase
- Même si les credentials sont présents, le code bloque l'écriture
- Protection contre les erreurs de configuration

## Logs DEV verbeux

Exemple de sortie :
```
[DEV] Fetching view page for nr 52000...
[DEV] nr 52000: Gate PASSED (Location de véhicule)
[DEV] nr 52000: Crawling 5 URLs: ['view', 'payment', 'logistic', 'infos', 'orders']
[DEV] nr 52000: Extraction complete - JSinfos: 3, Basket lines: 5, Explorer links: 12, Time: 2.34s
Saved summary to data/dev/52000/summary.json
Saved extracted data to data/dev/52000/extracted.json
```

## Mode PROD

- `--resume` activé par défaut
- Paramètres optimisés pour long run
- Logs moins verbeux (INFO level)

