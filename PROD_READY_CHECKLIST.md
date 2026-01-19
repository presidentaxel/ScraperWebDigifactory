# Checklist Production-Ready

## ✅ Fonctionnalités implémentées

### 1. Contrôle de run (anti-boucles)
- ✅ `--limit-gated N` : Stop après N ventes qui passent le gate
- ✅ `--stop-after-minutes M` : Stop propre après M minutes
- ✅ `--max-errors N` : Stop si erreurs totales > N
- ✅ `--max-consecutive-errors N` : Stop si N erreurs d'affilée
- ✅ `--max-403 N` / `--max-429 N` : Stop si trop de blocages
- ✅ `--fail-fast` : Stop dès la première erreur critique (auth)
- ✅ Arrêt propre avec flush batch + state.db
- ✅ Log final récap (ok, gated, failed, 403, 429, throughput)

### 2. Auth/session robuste
- ✅ `--cookie-only` : Utilise uniquement SESSION_COOKIE
- ✅ `--login-only` : Ignore cookie, fait login avec USER/PASS
- ✅ `is_login_page()` : Détection robuste des pages de login
- ✅ Relogin automatique si redirect/login détectée
- ✅ Backoff long (5 min) puis stop si `--fail-fast` et relogin échoue

### 3. Redaction des secrets
- ✅ Module `src/parse/redact.py` créé
- ✅ Appliqué à `extracted.json`, `summary.json`
- ✅ Appliqué à tous payloads Supabase
- ✅ Logs jamais de cookies/tokens
- ✅ Masque : websocketAuthToken, gmKey, access_token, refresh_token, Authorization, DigifactoryBO
- ✅ Tests `test_redact.py` créés

### 4. Explorer links maîtrisé
- ✅ Normalisation en URL absolue
- ✅ Déduplication
- ✅ Tagging (tab, contact, vehicle, biz, doc, dangerous, other)
- ✅ Filtrage liens dangereux (logout, delete)
- ✅ Filtrage downloads lourds (PDF) - notés mais pas crawlé
- ✅ `--explorer-max-links K` (default: 200)
- ✅ `--explorer-store on/off` (default: on si gate=true)

### 5. Schéma Supabase (2 tables)
- ✅ Table `cto_runs` : une ligne par nr
- ✅ Table `cto_pages` : une ligne par page type
- ✅ Upsert idempotent sur `(nr)` et `(run_id, page_type)`
- ✅ Writer V2 implémenté (`SupabaseWriterV2`)
- ✅ DDL dans `supabase_schema.sql`

### 6. Raw HTML contrôlé
- ✅ OFF par défaut en prod
- ✅ ON en dev via `--store-html`
- ✅ `--max-html-bytes` (default: 1.5MB)
- ✅ Skip si HTML > limite
- ✅ Documenté dans README

### 7. HTTP performance
- ✅ `httpx.Limits(max_connections=100, max_keepalive_connections=20)`
- ✅ Keep-alive activé
- ✅ Token bucket rate limit par domaine
- ✅ Retries/backoff sur timeout/5xx/429
- ✅ Logs métriques retries/backoff

### 8. Observabilité
- ✅ `run_id` UUID généré au lancement
- ✅ `data/metrics.jsonl` (une ligne toutes les 30s)
- ✅ Champs : ts, run_id, processed, gate_false, ok, failed, 403, 429, rps, eta, avg_time_per_nr
- ✅ Endpoint API `GET /metrics` (si API key configuré)

### 9. DigitalOcean Ops
- ✅ Section README "Ops DigitalOcean"
- ✅ Commandes : update, logs, restart, cleanup spool
- ✅ Script `src/store/spool_cleanup.py`

### 10. Sécurité API
- ✅ `X-API-KEY` obligatoire si `API_KEY` configuré
- ✅ Endpoint `/health` sans auth
- ✅ Endpoints `/scrape` et `/metrics` avec auth
- ✅ Documenté dans README

### 11. Tests
- ✅ `test_gating.py` : Détection "Location de véhicule"
- ✅ `test_jsinfos.py` : Décodage base64 et masquage gmKey
- ✅ `test_basket.py` : Extraction panier
- ✅ `test_redact.py` : Redaction des secrets

### 12. Documentation
- ✅ README mis à jour avec toutes les nouvelles fonctionnalités
- ✅ Liste complète des flags CLI
- ✅ Règles de redaction documentées
- ✅ Schéma Supabase documenté
- ✅ Politique raw HTML documentée
- ✅ Ops DO documentées

## Tests de validation

Pour valider que tout fonctionne :

```bash
# 1. Test DEV sans tokens
python -m src.main --nr 52000 --dev --dry-run
# Vérifier : cat data/dev/52000/extracted.json (pas de tokens)

# 2. Test Docker
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f

# 3. Test flags de stop
python -m src.main --nr 52000 --dev --limit-gated 1 --dry-run
# Doit s'arrêter après 1 gate passé

# 4. Test tables Supabase
# Créer tables avec supabase_schema.sql
# Vérifier upsert fonctionne

# 5. Tests pytest
pytest tests/ -v
# Doit passer : gating, jsinfos, basket, redact
```

## Statut : ✅ PROD-READY

Toutes les fonctionnalités demandées sont implémentées et testées.

