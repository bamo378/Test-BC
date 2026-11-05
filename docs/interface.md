# Interface PolyImmo

L’interface française utilise les couleurs noir, blanc et rouge, six onglets avec liens directs, un thème sombre mémorisé et une navigation mobile fixe. Les préférences locales et les scénarios sauvegardés ont des rôles distincts.

## Fonctions disponibles

- **Vue d’ensemble** : productions jour/semaine/mois/cumul, puissance AC, dernières journées, récupération estimée de l’investissement ; widgets personnalisables et mode mural.
- **Production** : puissance/énergie ; vues Jour/Semaine/Mois/Année ; dates libres ; courbe/barres ; zoom ; comparaison de période précédente ; favoris conservés sur l’appareil ; calendrier des mesures disponibles. Infobulles souris, tactile et clavier ; exports CSV et SVG.
- **Finances** : année, recherche insensible aux accents, relevés détaillés, encaissements trimestriels, prix moyen pondéré, investissement et bilan annuel. Les relevés GRD et la production Aurora restent séparés.
- **Saisie** : nouveaux relevés mensuels/trimestriels GRD, encaissement bancaire sur le même relevé, autres recettes, charges, références de documents, modification, archivage/restauration et contrôle des doublons. Les pièces ne sont pas téléversées ou analysées automatiquement.
- **Projection** : trente ans, baisse de production, évolution des tarifs, charges, inflation, remplacement d’onduleur, bases saisonnières et **tarif en ct CHF/kWh de chaque trimestre futur**. Application annuelle/tout futur, reconduction, comparaison Excel, sauvegarde/rechargement des hypothèses, exports trimestriels et rapport PDF local au site.
- **Données & suivi** : dates de dernière tentative/réussite/mesure, fraîcheur, reconnexion, provenance et couverture historique réellement vérifiée par année, incohérences à rapprocher.

Le guide détaillé GRD → banque → charges et des tarifs est `saisie-projections.md`.

## Calculs et périodes absentes

Les filtres utilisent les mesures réellement conservées. La puissance est disponible à 15 minutes ; une moyenne horaire exige ses quatre intervalles. L’énergie quotidienne peut être regroupée par semaine ou mois ; les groupes incomplets restent signalés. Les lacunes interrompent les courbes de puissance **et d’énergie**. Le calendrier inclut les années sans données, dont 2024. Aucun trou n’est remplacé par zéro et aucun pourcentage global n’est affiché si sa comparaison est incomplète.

L’historique financier initial reste celui du classeur. Les nouvelles saisies complètent ses périodes suivantes sans modifier l’original. Les montants attendus ne sont pas additionnés aux encaissements. Un trimestre partiel conserve une projection entière, avec informations connues à part ; un trimestre complet et soldé utilise ses réalisations et verrouille ses prix.

Le scénario initial a été rapproché des résultats mémorisés du classeur. Le TRI standard sépare l’investissement initial des flux de fin d’année ; sa convention diffère de celle du fichier. Les charges historiques absentes sont explicitement supposées nulles. Les prix de référence sont réalisés, pas des tarifs contractuels confirmés. Les résultats financiers restent privés.

Les vues et le brouillon sont mémorisés localement. Les scénarios explicitement sauvegardés vont dans SQLite ; ils conservent des hypothèses qui seront réappliquées aux données réalisées courantes.

## Logo et validation

Le logo visible dans la conversation n’existe pas comme fichier local accessible. Le nom PolyImmo noir/rouge reste provisoire ; l’interface détecte `polyimmo/static/logo-polyimmo.png` ou `.svg` dès ajout de l’original, sans le redessiner.

25 tests Python, 13 tests JavaScript et le parcours Chromium des six onglets à cinq largeurs ont réussi. Les ajouts financiers d’essai restent dans une base temporaire. Captures réelles : `.local/final-overview.png`, `final-production.png`, `final-entries.png`, `final-entry-form.png`, `final-projection.png`, `final-sources.png` et versions mobiles. Le protocole et les limites publiables sont dans `sources.md` ; les résultats chiffrés restent dans la documentation privée.

Le serveur et la collecte fonctionnent dans Codex. L’hébergement permanent et l’authentification du site restent à mettre en place ; les captures sont des aperçus, pas un lien public de production.
