> Le mode gratuit GitHub Pages est maintenant préparé : voir [le guide Pages](github-pages.md). Ce document décrit le mode serveur Python alternatif.

# Préparation de l’hébergement

**Mise à jour après connexion :** la collecte réelle est maintenant validée dans Codex et un processus horaire y a été lancé. Les prérequis réseau et secrets de cette instance sont résolus. L’offre d’hébergement de production reste inconnue : GitHub est le seul service identifié avec l’utilisateur. Les étapes ci-dessous concernent une future production, pas un site déjà publié.

Trois modèles sont fournis dans `deploy/` : deux services systemd séparés pour le web et le collecteur, et un exemple Caddy pour HTTPS avec authentification de tout le site. Ils ciblent `/opt/polyimmo` pour le code et `/var/lib/polyimmo` pour la base persistante. Ils ne sont ni installés ni validés sur un hébergeur, qui reste à choisir. Les adapter et les tester avant activation. L’authentification du site est distincte d’Aurora ; elle protège aussi `/api/`.

Le fichier privé `/etc/polyimmo/aurora.env` attendu sur ce futur serveur doit être configuré par un moyen sécurisé, permissions 0600, avec les deux secrets de connexion. Aucun fichier contenant des valeurs n’est fourni dans Git. Hors Codex, les placeholders du proxy ne sont pas exportables comme identifiants : l’hébergeur doit recevoir ses propres valeurs par son coffre sécurisé. Caddy attend un domaine réel, un nom d’accès au site et un hash de mot de passe généré de façon sûre ; aucun de ces choix n’est inventé ici.

## Environnement constaté

Le dépôt GitHub `bamo378/Test-BC` était sans commit ni code. Le service identifié par l’utilisateur est GitHub ; aucun hébergement de production précis n’est confirmé. La machine Codex est un environnement de développement : Python, SQLite via Python, FastAPI, Uvicorn, openpyxl, Chromium et Playwright y sont disponibles. Aucun service PostgreSQL, serveur web de production ou déploiement existant n’a été identifié dans le dépôt. Les noms des variables et la configuration cloud ont été inspectés sans lire de valeurs secrètes ; cela ne permet pas de conclure à l’existence d’un compte d’hébergement autorisé à déployer.

Le site est vérifié localement uniquement. La publication du code sur GitHub est distincte du déploiement. Aucune dépense, création de compte fournisseur, mise en ligne publique ou modification DNS n’est effectuée.

## Architecture proposée

```text
Navigateur d’administration privé → connexion normale Aurora Vision
                                      ↓ session privée
Planificateur → collecteur serveur → base persistante → API privée → interface française
                     ↘ état de collecte / reconnexion requise ↗
```

Pour cette seule installation, un petit serveur Linux ou service de conteneurs avec **volume persistant et exécution de tâches en arrière-plan** est une option adaptée. La validation du portail a établi qu’un client HTTP serveur suffit : aucun navigateur permanent n’est nécessaire. SQLite convient à un serveur unique avec peu d’écritures ; ne pas placer le fichier sur un disque éphémère ou le partager entre plusieurs réplicas. PostgreSQL devient utile si plusieurs instances ou un service managé l’exigent. La base existante n’a pas besoin d’un serveur SQLite séparé.

GitHub héberge le code. **GitHub Pages ne peut pas exécuter le collecteur ni protéger une session Aurora.** Un hébergement statique seul est donc insuffisant. Le choix du fournisseur, son offre, sa région, son coût et le domaine final restent à arrêter une fois la collecte validée. Ne pas proposer de coût précis sans offre vérifiée. Par défaut, préparer un site privé ; son caractère public n’a pas encore été choisi par l’utilisateur.

## Installation et démarrage testés dans Codex

Depuis `/workspace/Test-BC` :

```sh
python -m pip install -r requirements.txt
# Import explicite d’un fichier privé fourni, sans le modifier :
python -m polyimmo.import_excel /chemin/prive/PolyImmo.xlsx
python -m uvicorn polyimmo.web:app --host 127.0.0.1 --port 8000 --no-access-log
```

Le chemin de l’Excel doit être remplacé par le vrai fichier. L’import n’est requis que lors d’un ajout/mise à jour de référence ; le snapshot et les dépendances installées sont conservés. Un réimport identique ne crée pas de doublon. La commande d’import effective sur la pièce jointe et un démarrage sur le port 8000 ont été vérifiés pendant le travail. Les tests utilisent des bases temporaires ; ils ne contiennent pas les données du client.

```sh
python -m unittest discover -s tests -v
curl --fail http://127.0.0.1:8000/healthz
```

`/healthz` atteste que le serveur et la base répondent, **pas** que la collecte fonctionne. Vérifier aussi `/api/dashboard`, le chargement mobile et les dates de synchronisation. Ne pas publier des liens localhost comme aperçu accessible de l’extérieur.

## Avant une mise en production

- Confirmer l’offre d’hébergement et les moyens d’accès sécurisés ; ne pas saisir de secret dans le chat.
- Revalider le connecteur sur l’hébergement choisi ; la cadence initiale est horaire, avec reprise des sept derniers jours. La reconnexion après perte locale de session est testée ; l’expiration naturelle longue durée reste à observer. Ne pas lancer plusieurs planificateurs sur la même base.
- Installer l’application sous un utilisateur dédié ; `POLYIMMO_DB` peut désigner un chemin de base privée, jamais sous le dossier des assets web. Configurer un volume persistant ; les cookies du collecteur restent uniquement en mémoire et sont renouvelés après redémarrage.
- Configurer HTTPS et une authentification du site, par exemple une passerelle OIDC éprouvée devant **toutes** les routes, y compris `/api/`. Garder Uvicorn sur loopback ; l’accès direct au port contournerait la passerelle. Le prototype n’implémente pas cette authentification et ne doit pas être exposé en l’état.
- Exécuter serveur et collecteur comme deux processus supervisés séparés ; le planificateur ne doit lancer qu’une collecte à la fois. Redémarrages indépendants, délais bornés et signalement d’échec. Ne jamais dépendre d’un processus vivant dans Codex après publication de l’environnement.
- Sauvegarder la base avec l’API `sqlite3.Connection.backup` ; chiffrer les sauvegardes et tester la restauration. Réduire et filtrer les journaux, pas de jeton/cookie/URL signée/identifiant de connexion dans les traces. Conserver les erreurs métier par code contrôlé.
- Tester récupération après arrêt, absence de réseau, session expirée, doublons, correction tardive, changement d’heure, retard de données et accès non authentifié rejeté.

Les configurations fournisseurs et la commande de déploiement seront finalisées à partir de l’hébergement effectivement choisi. Les modèles fournis ne prouvent pas un déploiement en production. La collecte fonctionne actuellement dans Codex ; aucune mise en ligne publique n’est annoncée.
