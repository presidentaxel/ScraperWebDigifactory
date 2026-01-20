# Comment faire tourner le scraper pendant des heures

## Problème identifié

Le scraper s'arrêtait après ~5 minutes avec "Interrupted by user" alors que vous n'aviez rien arrêté. Cela peut être causé par :
- Une exception non gérée qui fait crasher le processus
- Une déconnexion SSH qui ferme le terminal
- Docker qui arrête le conteneur

## Solutions appliquées

✅ **Gestion d'exceptions améliorée** : Le scraper continue même si une erreur survient dans un chunk
✅ **Logging amélioré** : Plus de détails sur les erreurs pour diagnostiquer
✅ **Robustesse** : Les erreurs dans un chunk n'arrêtent plus tout le processus

## Comment lancer pour tourner pendant des heures

### Option 1 : Avec `nohup` (recommandé)

```bash
# Lancer en arrière-plan avec nohup
nohup docker compose -f docker-compose.prod.yml exec scraper-api python -m src.main --start 4 --end 57561 --write-supabase --no-resume > scraper.log 2>&1 &

# Voir les logs en temps réel
tail -f scraper.log

# Vérifier que ça tourne
ps aux | grep python
```

### Option 2 : Avec `screen` (meilleur pour monitoring)

```bash
# Installer screen si nécessaire
apt install screen

# Créer une session screen
screen -S scraper

# Lancer la commande dans screen
docker compose -f docker-compose.prod.yml exec scraper-api python -m src.main --start 4 --end 57561 --write-supabase --no-resume

# Détacher : Ctrl+A puis D
# Reconnecter : screen -r scraper
# Lister les sessions : screen -ls
```

### Option 3 : Avec `tmux` (alternative à screen)

```bash
# Installer tmux si nécessaire
apt install tmux

# Créer une session tmux
tmux new -s scraper

# Lancer la commande
docker compose -f docker-compose.prod.yml exec scraper-api python -m src.main --start 4 --end 57561 --write-supabase --no-resume

# Détacher : Ctrl+B puis D
# Reconnecter : tmux attach -t scraper
```

### Option 4 : Directement dans Docker (avec restart policy)

Modifier `docker-compose.prod.yml` pour ajouter une commande qui tourne en boucle :

```yaml
services:
  scraper-api:
    # ... existing config ...
    restart: always  # Au lieu de unless-stopped
    command: python -m src.main --start 4 --end 57561 --write-supabase --no-resume
```

Puis lancer :
```bash
docker compose -f docker-compose.prod.yml up -d scraper-api
docker compose -f docker-compose.prod.yml logs -f scraper-api
```

## Surveillance

### Vérifier que ça tourne toujours

```bash
# Voir les processus Python
ps aux | grep python

# Voir les logs Docker
docker compose -f docker-compose.prod.yml logs --tail=100 -f scraper-api

# Vérifier l'utilisation mémoire/CPU
docker stats digifactory-scraper-api
```

### Vérifier la progression dans Supabase

```sql
-- Voir combien de records ont été traités
SELECT COUNT(*) FROM cto_runs WHERE nr >= 4 AND nr <= 57561;

-- Voir les derniers records traités
SELECT nr, gate_passed, status, started_at, finished_at 
FROM cto_runs 
WHERE nr >= 4 AND nr <= 57561 
ORDER BY started_at DESC 
LIMIT 20;
```

## Si ça s'arrête encore

1. **Vérifier les logs** pour voir la raison exacte :
   ```bash
   docker compose -f docker-compose.prod.yml logs scraper-api | tail -100
   ```

2. **Vérifier la mémoire** :
   ```bash
   free -h
   docker stats digifactory-scraper-api
   ```

3. **Vérifier les erreurs dans Supabase** :
   ```sql
   SELECT * FROM cto_errors ORDER BY occurred_at DESC LIMIT 20;
   ```

4. **Relancer avec resume** :
   ```bash
   docker compose -f docker-compose.prod.yml exec scraper-api python -m src.main --start 4 --end 57561 --write-supabase --resume
   ```

## Recommandation finale

**Utilisez `screen` ou `tmux`** - c'est la meilleure solution pour :
- ✅ Garder la session active même si SSH se déconnecte
- ✅ Pouvoir reconnecter facilement pour voir les logs
- ✅ Détacher/attacher à volonté
- ✅ Surveiller en temps réel

