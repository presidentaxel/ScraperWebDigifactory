# Troubleshooting Guide

## Problème : Login ne trouve pas le cookie de session

### Symptômes
```
Login failed: No session cookie found in login response
```

### Solutions

#### Option 1 : Utiliser un cookie de session manuel (recommandé)

1. **Ouvrir DigiFactory dans votre navigateur**
2. **Se connecter manuellement**
3. **Extraire le cookie** :
   - Chrome/Edge : F12 → Application → Cookies → Copier la valeur de `DigifactoryBO`
   - Firefox : F12 → Storage → Cookies → Copier la valeur de `DigifactoryBO`

4. **Ajouter dans `.env`** :
```bash
SESSION_COOKIE=DigifactoryBO=votre_valeur_ici
```

5. **Utiliser `--cookie-only`** :
```bash
python -m src.main --nr 52000 --dev --dry-run --cookie-only
```

#### Option 2 : Vérifier le formulaire de login

Le formulaire DigiFactory peut utiliser des noms de champs différents. Vérifier dans le HTML de la page de login :

1. Ouvrir `https://entrepreneur.digifactory.fr/digi/com/login` dans le navigateur
2. Inspecter le formulaire (F12)
3. Noter les noms des champs `name` ou `id`

Si les champs sont différents (ex: `login` au lieu de `username`), modifier `src/auth/session.py` :

```python
login_data = {
    "login": config.USERNAME,  # ou le nom réel du champ
    "password": config.PASSWORD,
}
```

#### Option 3 : Activer le mode debug

Ajouter dans `.env` :
```bash
LOG_LEVEL=DEBUG
```

Puis relancer pour voir les détails de la réponse de login.

### Vérification

Pour vérifier que le cookie fonctionne :

```bash
# Test avec cookie manuel
python -m src.main --nr 52000 --dev --dry-run --cookie-only

# Si ça fonctionne, vous verrez :
# [INFO] Using provided session cookie (cookie-only mode)
# [INFO] [DEV] nr 52000: Gate PASSED/FAILED
```

## Autres problèmes courants

### Session expirée pendant le scraping

Le scraper détecte automatiquement l'expiration et tente un relogin. Si cela échoue :

1. Vérifier que `USERNAME`/`PASSWORD` sont corrects
2. Utiliser `--cookie-only` avec un cookie frais
3. Réduire `--stop-after-minutes` pour relancer plus souvent

### 403 Forbidden

- Vérifier que le cookie de session est valide
- Réduire `CONCURRENCY` et `RATE_PER_DOMAIN`
- Utiliser `--max-403 5` pour arrêter si trop de 403

### 429 Too Many Requests

- Réduire `CONCURRENCY` (ex: 10 au lieu de 20)
- Réduire `RATE_PER_DOMAIN` (ex: 1 au lieu de 2)
- Utiliser `--max-429 10` pour arrêter si trop de 429

