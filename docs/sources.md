# Sources et calculs

## Classeur de référence

Le classeur privé est analysé et importé sans modification. Il fournit les relevés financiers, l’investissement, les charges renseignées et les hypothèses. L’audit exhaustif (feuilles, cellules, formules et graphiques) reste dans `.local/excel-audit.json`. L’analyse chiffrée détaillée et les preuves de collecte sont conservées hors Git ; elles ne doivent pas être publiées avec le code.

Le site sépare production Aurora, injection du distributeur et énergie des relevés financiers. Les montants attendus GRD, encaissements et autres recettes sont distincts. Un prix réalisé est le ratio pondéré encaissements / énergie, exprimé en ct CHF/kWh ; il n’est pas automatiquement un tarif contractuel.

Les données absentes restent inconnues. La convention historique de charges nulles est signalée explicitement dans les calculs. Une présence partielle ne suffit pas à valider un mois, trimestre ou exercice complet. Voir [le guide de saisie](saisie-projections.md).

## Collecte Aurora en lecture seule

Le connecteur serveur suit la connexion normale du portail sur `www.auroravision.net`, avec les variables sécurisées `AURORA_LOGIN` et `AURORA_PASSWORD`. Aucun identifiant n’est renseigné dans le dépôt, aucune clé API FIMER ni connexion directe aux onduleurs n’est utilisée.

Requêtes observées puis testées réellement : connexion `/ums/v1/login?setCookie=true`, énergie `GenerationEnergy` avec agrégations `Day`/`All` et `afx=Delta`, puissance `GenerationPower` avec `agp=Min15` et `afx=Avg`. Les bornes `sdt`/`edt` sont UTC. Les réponses métier comportent début, fin, unité et valeur. Les cookies restent en mémoire du client HTTP ; le navigateur des visiteurs n’appelle jamais Aurora.

L’énergie est exprimée en kWh ; la puissance est convertie de W en kW. Les intervalles en cours/futurs sont exclus de l’historique achevé. Les puissances négatives renvoyées sont conservées ; les énergies négatives sont écartées et signalées. Une valeur absente n’est pas zéro. Les bornes quotidiennes sont contrôlées dans Europe/Zurich ; une réponse incorrecte au changement d’heure nécessite un agrégat exact de 23/25 heures, pas une simple correction artificielle de durée.

La collecte courante reprend sept jours. Le module `polyimmo.history` reprend une plage explicite de jours achevés et enregistre couverture, valeurs rejetées et rapprochement avec l’agrégat. Une clé d’unicité installation/appareil/métrique/début UTC/durée évite les doublons ; les corrections gardent une révision. Un historique partiel ne devient pas complet par l’import.

Les erreurs transitoires ont des tentatives bornées. Retry-After est respecté et une session refusée permet une réauthentification normale unique. Une perte locale de cookies a été testée ; l’expiration naturelle prolongée et le fonctionnement durable sur l’hébergeur choisi restent à vérifier. Aucun rapport n’est créé ou programmé, aucun accord ni réglage Aurora n’est modifié.

## Validation et limites

La connexion normale, un export CSV du tableau de bord et un client serveur indépendant ont été rapprochés sur des journées achevées. L’historique a été interrogé : certaines périodes demeurent absentes ou non concordantes. Les résultats détaillés restent privés. Une différence de source ne prouve pas sa cause ; ne pas fusionner production et facturation.

25 tests Python et 13 tests JavaScript ont réussi. Les essais de saisie utilisent une copie temporaire ; les parcours navigateur ont vérifié six onglets à cinq largeurs. Ces tests ne remplacent pas les contrôles sur l’hébergement de production. Celui-ci nécessite encore HTTPS, authentification de toutes les routes, disque persistant, supervision et sauvegarde/restauration.
