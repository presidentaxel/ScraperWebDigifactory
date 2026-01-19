# Guide de démarrage rapide

## 1. Installation locale

```bash
# Installer les dépendances
pip install -r requirements.txt

# Configurer .env
cp env.example.txt .env
# Éditer .env avec vos credentials
```

## 2. Tester le gating

```bash
# Tester avec un nr connu
python -m src.main --start 52000 --end 52000 --concurrency 1
```

Vérifier dans les logs :
- `Gate passed` = extraction complète des 5 pages
- `Gate failed` = enregistrement minimal

## 3. Lancer l'API

```bash
# Mode développement
uvicorn src.api.main:app --reload

# Tester
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"nr": 52000}'
```

## 4. Déploiement Docker

```bash
# Build et start
docker-compose up -d

# Voir les logs
docker-compose logs -f

# Tester
curl http://localhost:8000/health
```

## 5. Déploiement DigitalOcean

### Sur un Droplet

```bash
# SSH dans le droplet
ssh root@your-droplet-ip

# Installer Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Cloner le projet
git clone <your-repo>
cd digifactory_scraper

# Configurer .env
nano .env

# Démarrer
docker-compose -f docker-compose.prod.yml up -d
```

## Points importants

1. **Gating** : Seules les pages avec "Location de véhicule" sont extraites complètement
2. **Session** : Utiliser `SESSION_COOKIE` si le login automatique ne fonctionne pas
3. **Supabase** : Créer la table avec `supabase_schema.sql` avant de lancer
4. **Logs** : Vérifier `scraper.log` pour les détails

## Structure des données

- **Gate failed** : `data.gate_passed = false`
- **Gate passed** : `data.gate_passed = true` + extraction complète

Voir `README.md` pour plus de détails.

