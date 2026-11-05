# Utiliser PolyImmo sur GitHub Pages, gratuitement

Adresse : **https://bamo378.github.io/Test-BC/**. Le fichier `index.html` ouvre le vrai tableau de bord ; `.nojekyll` évite que GitHub transforme le README en page d’accueil.

## Votre Excel et vos nouvelles saisies

1. Ouvrir le site et choisir **Ouvrir mon fichier Excel**. Sélectionner le classeur PolyImmo fourni : lecture locale, aucun envoi à GitHub.
2. Dans **Saisie**, utiliser les formulaires existants **Ajouter un relevé** et **Ajouter une charge**. Une banque complète le même relevé GRD, avec montant attendu et montant reçu distincts. Les autres revenus gardent leur champ existant.
3. Les formulaires, graphiques, filtres et projections déjà créés sont conservés ; seul le stockage change. Les modifications, l’archivage et la restauration continuent à fonctionner.
4. Dans **Mes données**, exporter régulièrement une **sauvegarde chiffrée** avec un mot de passe distinct d’au moins 12 caractères. Pour changer d’appareil, y ouvrir la sauvegarde avec le même mot de passe.

Les données sont conservées dans IndexedDB, pour ce navigateur et cette origine. Pas de synchronisation automatique des saisies entre appareils. Effacer les données du navigateur, changer de navigateur ou utiliser la navigation privée peut supprimer ce stockage : une sauvegarde téléchargée est nécessaire. Aucun jeton GitHub n’est demandé aux visiteurs ; les données financières ne sont jamais écrites dans un fichier public du dépôt.

Les périodes des relevés GRD restent mensuelles ou trimestrielles ; charges et versements conservent leurs dates existantes. Le montant bancaire est le **total reçu pour la période**, pas une nouvelle somme à additionner à chaque modification. Les périodes déjà importées de l’Excel sont protégées contre les doublons.

## Activer la collecte automatique Aurora

Le navigateur visiteur ne reçoit jamais les identifiants ou cookies Aurora. Le programme Python s’exécute sur les serveurs GitHub Actions ; il publie uniquement un fichier chiffré AES-256-GCM. La passphrase de données est distincte du compte Aurora et est saisie par le propriétaire pour déverrouiller les mesures dans son navigateur.

### Un seul réglage Pages

Ouvrir **[Settings → Pages](https://github.com/bamo378/Test-BC/settings/pages)**. Dans **Build and deployment → Source**, choisir **GitHub Actions**. L’adresse publique reste la même. Il n’est pas nécessaire d’acheter un domaine ou un hébergement.

### Trois secrets du dépôt, jamais dans la conversation ou le code

Dans **[Settings → Secrets and variables → Actions](https://github.com/bamo378/Test-BC/settings/secrets/actions)**, choisir **New repository secret** et renseigner :

- `AURORA_LOGIN` : votre adresse de connexion Aurora ;
- `AURORA_PASSWORD` : votre mot de passe Aurora ;
- `POLYIMMO_DATA_PASSWORD` : un **nouveau mot de passe distinct**, d’au moins 12 caractères, servant uniquement au chiffrement des données du site.

Les secrets renseignés dans Codex ne sont pas transférés automatiquement à GitHub. Ne pas coller de cookie, de session ou de placeholder du proxy Codex. Conserver la passphrase de données : sans elle, les mesures publiées restent illisibles. Pour changer cette passphrase, préparer d’abord un transfert de l’historique ; ne pas changer le secret sans migration, car l’ancien fichier ne pourrait plus être déchiffré.

### Premier test réel à terminer

Ouvrir **[Actions → Site PolyImmo et collecte chiffrée](https://github.com/bamo378/Test-BC/actions/workflows/pages.yml)**, puis **Run workflow** sur `main`. Contrôler la réussite de `build` et `deploy`. Le premier passage reprend l’historique disponible ; les absences et les valeurs rejetées restent signalées. Sans les trois secrets, seul le site est déployé et la collecte est marquée non activée.

Sur le site, **Mes données → Mesures automatiques Aurora**, saisir uniquement `POLYIMMO_DATA_PASSWORD`. Vérifier les dates de collecte et de dernière mesure. Cette étape constitue le test de bout en bout sur GitHub ; elle ne doit pas être annoncée réussie avant son exécution réelle.

La cadence prévue est horaire, avec la planification GitHub (des retards restent possibles). L’interface signale les données anciennes au-delà de trois heures. La reprise évite les doublons et conserve le dernier succès en cas d’échec. Le fichier chiffré précédent est relu avant un nouveau déploiement ; un problème de lecture/déchiffrement bloque la publication plutôt que de supprimer l’historique.

## Coût et limites

Le site utilise GitHub Pages et les runners Linux standard de GitHub Actions, sans souscription à un hébergeur tiers. Respecter les quotas et conditions du compte GitHub ; ne pas activer de runner payant ni d’options facturées. Les tâches planifiées peuvent être retardées ou désactivées par GitHub après une longue inactivité du dépôt : contrôler les dates affichées et réactiver le workflow si nécessaire.

Le chiffrement protège le contenu des mesures publiques ; la robustesse dépend du mot de passe distinct choisi, qui doit être long et difficile à deviner. Les sauvegardes et les fichiers XLSX ne sont pas publiés. Aucun rapport Aurora n’est créé, aucune configuration du portail modifiée.
