# Recommandations d'Optimisation de Vitesse

## Paramètres à ajuster dans `.env` ou `docker-compose.prod.yml`

### 🚀 Configuration Agressive (recommandée si 0 reconnexions)

```bash
# Augmenter la concurrence (plus de requêtes parallèles)
CONCURRENCY=50

# Augmenter le taux de requêtes par seconde
RATE_PER_DOMAIN=5.0

# Augmenter le batch size pour moins de flushes Supabase
BATCH_SIZE=5000

# Timeout peut rester à 20 (suffisant)
TIMEOUT=20
```

### ⚡ Configuration Très Agressive (si serveur DigiFactory le supporte)

```bash
CONCURRENCY=100
RATE_PER_DOMAIN=10.0
BATCH_SIZE=10000
TIMEOUT=20
```

### 📊 Explication des paramètres

#### CONCURRENCY (20 → 50-100)
- **Impact** : ⭐⭐⭐⭐⭐ (très élevé)
- **Effet** : Plus de requêtes HTTP simultanées
- **Risque** : Peut déclencher des "Double session" si trop élevé
- **Recommandation** : Commencer à 50, monter progressivement

#### RATE_PER_DOMAIN (2.0 → 5.0-10.0)
- **Impact** : ⭐⭐⭐⭐ (élevé)
- **Effet** : Plus de requêtes par seconde vers le même domaine
- **Risque** : Peut déclencher des rate limits (429)
- **Recommandation** : Commencer à 5.0, monter à 10.0 si stable

#### BATCH_SIZE (1000 → 5000-10000)
- **Impact** : ⭐⭐ (moyen)
- **Effet** : Moins de flushes vers Supabase = moins de latence
- **Risque** : Plus de données perdues en cas de crash
- **Recommandation** : 5000 est un bon compromis

#### TIMEOUT (20)
- **Impact** : ⭐ (faible)
- **Effet** : Temps d'attente avant abandon
- **Recommandation** : Garder à 20 (suffisant)

## Comment appliquer

### Option 1 : Variables d'environnement dans `.env`
```bash
CONCURRENCY=50
RATE_PER_DOMAIN=5.0
BATCH_SIZE=5000
TIMEOUT=20
```

### Option 2 : Directement dans la commande Docker
```bash
docker compose -f docker-compose.prod.yml exec -e CONCURRENCY=50 -e RATE_PER_DOMAIN=5.0 -e BATCH_SIZE=5000 scraper-api python -m src.main --start 5994 --end 57561 --write-supabase --no-resume
```

### Option 3 : Modifier `docker-compose.prod.yml`
```yaml
environment:
  - CONCURRENCY=50
  - RATE_PER_DOMAIN=5.0
  - BATCH_SIZE=5000
```

## Monitoring

Surveillez ces indicateurs pour ajuster :
- **"Double session" popups** → Réduire CONCURRENCY
- **429 errors** → Réduire RATE_PER_DOMAIN
- **Network errors** → Vérifier TIMEOUT et connexion réseau
- **Throughput** → Augmenter progressivement si stable

## Calcul de vitesse estimée

Avec `CONCURRENCY=50` et `RATE_PER_DOMAIN=5.0` :
- **Théorique** : ~250 requêtes/seconde (50 × 5.0)
- **Réel** : ~100-150 requêtes/seconde (avec latence réseau)
- **Pour 51568 records** : ~5-8 minutes (au lieu de 20-30 minutes)

## Progression recommandée

1. **Étape 1** : `CONCURRENCY=30, RATE_PER_DOMAIN=3.0` → Tester 5 minutes
2. **Étape 2** : `CONCURRENCY=50, RATE_PER_DOMAIN=5.0` → Tester 10 minutes
3. **Étape 3** : `CONCURRENCY=75, RATE_PER_DOMAIN=7.5` → Tester 15 minutes
4. **Étape 4** : `CONCURRENCY=100, RATE_PER_DOMAIN=10.0` → Si stable

Si vous voyez des erreurs, revenez à l'étape précédente.

