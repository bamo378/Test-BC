# PolyImmo — suivi photovoltaïque

Site privé en français pour ordinateur et téléphone. **La connexion Aurora Vision et la récupération côté serveur ont été validées le 5 novembre 2026**, contre un véritable export CSV du tableau de bord. Le site n’est pas encore hébergé en production. Le code est séparé des données privées et de la configuration de l’environnement Codex.

L’interface noir/blanc/rouge comporte six onglets : vue d’ensemble, production, finances, **saisie GRD/banque/charges**, projection et suivi des sources. Filtres jour/semaine/mois/année, dates libres, zoom, comparaison, calendrier, favoris, thèmes, accueil personnalisable, mode mural et exports CSV/SVG/PDF sont disponibles. Les projections permettent un tarif en **ct CHF/kWh pour chaque trimestre futur**, des bases saisonnières, une recopie par année et des scénarios sauvegardés en base privée.

Les montants attendus du GRD et les encaissements bancaires sont séparés. La banque complète le même relevé ; les chevauchements sont rejetés. L’Excel original reste inchangé. Les tests de saisie utilisent une base temporaire, jamais le suivi réel.

Le logo original fourni dans le dépôt de référence Polyimmo est intégré sous `polyimmo/static/logo-polyimmo.png`.

## GitHub Pages : le site gratuit

Le vrai tableau de bord s’ouvre sur **https://bamo378.github.io/Test-BC/**. Il fonctionne directement dans le navigateur : import privé du classeur, formulaires existants de saisie GRD/banque/autres revenus/charges, filtres et projections. Le logo original est intégré. Les données financières restent dans IndexedDB ; les sauvegardes chiffrées permettent de changer d’appareil. Aucun jeton GitHub ou identifiant Aurora n’est demandé aux visiteurs.

La collecte automatique est préparée dans GitHub Actions et publie uniquement des mesures chiffrées. Son activation requiert trois secrets GitHub et la source Pages « GitHub Actions ». Le test de bout en bout après activation reste nécessaire. **[Guide complet et activation](docs/github-pages.md)**.

Le serveur Python ci-dessous reste une autre façon d’utiliser le projet ; il n’est pas nécessaire pour les saisies sur GitHub Pages.

## Démarrage privé

```sh
cd /workspace/Test-BC
python -m pip install -r requirements.txt
# Seulement pour importer une référence réelle disponible :
python -m polyimmo.import_excel /chemin/prive/PolyImmo.xlsx
python -m uvicorn polyimmo.web:app --host 127.0.0.1 --port 8000 --no-access-log
```

Dans une seconde session, avec `AURORA_LOGIN` et `AURORA_PASSWORD` fournis par les paramètres sécurisés de l’environnement :

```sh
python -m polyimmo.collector --loop --interval 3600
```

Une collecte ponctuelle : `python -m polyimmo.collector`. Un verrou empêche deux collecteurs sur la même base. Le connecteur suit la connexion normale du portail : aucune clé API FIMER, aucun accès aux onduleurs, aucun rapport ni changement de réglage. Les cookies restent en mémoire ; une session refusée entraîne une reconnexion normale unique. Ne jamais passer un secret en argument ni l’ajouter dans Git.

La collecte reprend sept journées achevées et la puissance AC à 15 minutes de la veille et du jour. Conversion W→kW explicite, puissances négatives conservées, intervalles futurs/en cours exclus. Les totaux jour/semaine/mois en cours sont partiels, distincts de l’historique quotidien. Fuseau Europe/Zurich, semaine commençant lundi. L’interface signale les données anciennes après trois heures, les erreurs et le besoin de reconnexion.

## Historique et stockage

SQLite : `.local/polyimmo.sqlite3`, ou chemin `POLYIMMO_DB`. Inventaire Excel : `.local/excel-audit.json`. Classeur, base, exports et captures sont privés et ignorés par Git. Réimport identique sans doublon ; les versions de référence sont séparées.

La disponibilité de l’historique quotidien a été contrôlée et varie selon les années. La couverture réelle par période est visible dans le site et stockée dans la base privée. Une donnée absente n’est jamais un zéro. Les bornes des journées de 23/25 heures sont vérifiées avec le portail. Les résultats chiffrés et l’analyse du classeur restent dans la documentation privée, hors Git.

Pour une reprise de plus de sept jours, choisir explicitement les dates achevées :

```sh
python -m polyimmo.history --start 2026-01-01 --end 2026-11-04
```

L’import est sans doublon, signale les périodes incomplètes et ne remplace pas la date du dernier succès live. Ne pas relancer tout l’historique sans besoin. Les données Aurora, les relevés financiers et l’archive d’injection GESA restent séparés. Les agrégats Aurora et l’Excel présentent des écarts non expliqués ; leur fusion serait trompeuse.

## Vérification et hébergement

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node tests/frontend.test.js
```

**28 tests Python et 16 tests JavaScript ont réussi**, plus les parcours Chromium des six onglets à cinq largeurs. Node sert aux tests ; aucun paquet npm ni compilation n’est requis pour servir l’application.

Dans le mode serveur Python, un hébergement avec stockage persistant et authentification est nécessaire. Dans le mode GitHub Pages, GitHub Actions exécute le collecteur et les données publiées sont chiffrées. Les modèles systemd et Caddy sous `deploy/` préparent un serveur unique avec stockage persistant, HTTPS et accès privé sur toutes les routes. Ils ne sont pas déployés. Uvicorn reste sur loopback jusque-là. Les secrets de cette instance Codex ne sont pas exportables vers un hébergeur : ses propres secrets devront être renseignés par un moyen sécurisé.

- [Sources, protocole de collecte et calculs](docs/sources.md)
- [Interface et fonctions](docs/interface.md)
- [Saisie GRD/banque et projections trimestrielles](docs/saisie-projections.md)
- [Préparation du déploiement](docs/deploiement.md)
