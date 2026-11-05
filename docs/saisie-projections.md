# Saisie mensuelle et projections trimestrielles

## Ajouter les informations reçues du GRD et de la banque

Ouvrir **Saisie**, puis **Ajouter un relevé**. Choisir une période mensuelle ou trimestrielle et renseigner uniquement les données réellement disponibles :

1. À réception du GRD : volumes haut/bas tarif, ou volume total si la ventilation est inconnue ; montant net attendu ; référence du document. Cocher la couverture complète seulement si les volumes couvrent toute la période. Laisser « Banque non renseignée » tant que le paiement n’est pas confirmé.
2. À réception de la banque : utiliser **Compléter / modifier sur la même ligne**. Renseigner le total réellement encaissé, le statut du paiement, sa dernière date connue et la référence bancaire. Le total est cumulatif en cas de plusieurs versements ; on ne crée pas un deuxième relevé pour le même mois.
3. Les montants attendus et encaissés sont distincts : seule la somme encaissée alimente les encaissements. Un montant manquant n’est pas transformé en zéro ; « pas encore encaissé » représente explicitement zéro reçu.
4. Les indemnités réellement reçues peuvent être ajoutées dans « Autres revenus ». Les références sont celles des pièces justificatives ; aucun identifiant de connexion bancaire n’est demandé.

Les fichiers PDF/Excel des organismes ne sont pas téléversés ou analysés automatiquement dans cet onglet. Il permet de saisir et conserver leurs références, volumes et montants. La récupération Aurora reste automatique, séparément.

Le découpage mensuel/trimestriel est contrôlé : un relevé trimestriel ne peut pas être ajouté par-dessus des mois déjà saisis. Une période déjà couverte par l’Excel est protégée. Dans le classeur actuel, les nouveaux relevés commencent après T3 2026. Pour corriger une erreur du fichier historique, traiter cette correction séparément plutôt que rajouter une ligne qui doublerait les volumes.

## Charges

**Ajouter une charge** permet de renseigner date, catégorie (entretien, assurance, nettoyage, frais GRD, autre), libellé, montant TTC et référence. Une charge future appartient aux hypothèses de projection, pas aux charges réalisées. Les frais déjà déduits d’un encaissement net ne doivent pas être saisis une seconde fois.

Les charges saisies complètent les charges du fichier ; elles ne garantissent pas l’exhaustivité de toutes les charges annuelles. Les relevés comme les charges peuvent être modifiés, archivés et restaurés. Les versions antérieures sont conservées dans une table de révisions ; l’Excel original n’est jamais modifié.

## Trimestres partiels et calculs

Un mois reçu ne transforme pas le trimestre entier en période réalisée. Le trimestre devient réalisé lorsque son relevé trimestriel complet, ou ses trois mois complets, et les paiements indiqués comme soldés sont présents.

Pendant un trimestre partiel :

- Les volumes et encaissements connus apparaissent immédiatement dans les finances et dans le suivi des saisies.
- La projection conserve une estimation du **trimestre entier**, avec les données connues affichées séparément. Elle n’ajoute pas les encaissements connus à une projection qui les inclurait déjà : pas de double comptage.
- Aucune répartition mensuelle de production n’est inventée à partir d’une moyenne trimestrielle. Si la projection est inférieure à un encaissement déjà connu, un message demande de revoir les hypothèses.
- Les prix moyens réalisés utilisent les relevés soldés avec volumes connus : une banque encore non renseignée ne fait pas artificiellement baisser un tarif réalisé.

Quand le trimestre est complet, ses volumes et encaissements réels remplacent sa projection et ses prix deviennent verrouillés. Les deux dernières années réellement complètes deviennent les références automatiques des projections ; la seule présence d’un mois ou d’une indemnité ne suffit pas. Un trimestre complet saisi au-delà d’un trou n’annule pas ce trou.

## Ajuster les ct/kWh de reprise

Ouvrir **Projection**, puis **Un tarif pour chaque trimestre**. Les unités sont des **centimes de CHF par kWh**.

- **Bases T1/T2/T3/T4** : valeurs saisonnières facultatives. Une case vide conserve le prix pondéré issu des références Excel ; ce prix réalisé n’est pas un tarif contractuel confirmé. L’évolution annuelle du prix s’applique à ces bases.
- **Tarif spécifique d’un trimestre**, par exemple T2 2028 : priorité absolue sur les bases et sur l’évolution annuelle. Le tarif saisi est fixe pour ce trimestre. Zéro est une vraie valeur, différente d’une case vide.
- **Appliquer à cette année** : renseigne uniquement ses trimestres projetés.
- **Appliquer à tout le futur** : renseigne tous les trimestres projetés sans modifier les périodes réalisées.
- **Reconduire aux années suivantes** : copie les tarifs effectifs de l’année sélectionnée vers les mêmes trimestres des années suivantes. Les tarifs source peuvent être des prix réalisés ou des hypothèses, ce qui doit être gardé à l’esprit.
- **Effacer les saisies spécifiques** : revient aux bases saisonnières et à leur évolution. **Hypothèses Excel** réinitialise aussi les autres paramètres.

Calcul : revenu projeté du trimestre = volume trimestriel projeté × tarif en ct/kWh / 100. Le volume vient des références de facturation ; il ne constitue pas automatiquement une production onduleurs ou une injection réellement mesurée pour le futur.

Un remplacement d’onduleur peut être renseigné par année et coût. Le bénéfice, le retour et le TRI se recalculent. Les trimestres réalisés gardent leurs données. Le TRI reste celui d’un investissement initial, suivi de flux annuels en fin d’année, distinct de la convention du fichier.

## Conserver, comparer et exporter

Le brouillon est mémorisé sur l’appareil. **Sauvegarder une copie** conserve les hypothèses et tarifs dans la base privée, avec un nom ; le scénario peut être rechargé après fermeture du navigateur. Il sauvegarde des hypothèses, pas une copie immuable de toutes les données financières : son chargement réutilise les données réalisées courantes. Un tarif d’un trimestre devenu réalisé est retiré des hypothèses obsolètes et ne modifie pas ce réalisé.

La courbe peut montrer la référence Excel en pointillés. Le détail trimestriel CSV indique volume, tarif, revenu, source du prix et données partielles déjà connues. **Rapport PDF** ouvre l’impression du navigateur : choisir « Enregistrer au format PDF ». Il produit un rapport local au site ; aucun rapport n’est créé ou programmé dans Aurora Vision.

## Autres options ajoutées

L’explorateur dispose des vues Jour/Semaine/Mois/Année, de la comparaison avec la période précédente et des vues favorites enregistrées sur l’appareil. Le calendrier distingue visuellement les journées mesurées des cases sans données ; cliquer une journée disponible ouvre sa sélection. Les pourcentages de comparaison restent indisponibles si la fenêtre commune est incomplète.

L’accueil est personnalisable et dispose d’un écran mural. Les alertes portent sur l’état de collecte et les mesures manquantes ; elles ne constituent pas un diagnostic de panne des onduleurs. Les historiques non récupérés restent explicitement indisponibles.

## Validation

28 tests Python et 16 tests JavaScript ont été exécutés avec succès. Le parcours Chromium complet a utilisé une **copie temporaire** de la base pour tester GRD → banque → charge → archivage/restauration, tarifs trimestriels et sauvegarde/rechargement des scénarios, favoris, calendrier, PDF et six sections à cinq largeurs d’écran. Aucun montant d’essai n’a été ajouté au suivi réel. Les captures et le rapport de référence destinés à l’utilisateur ont ensuite été produits avec les seules données réelles.

L’interface et la collecte fonctionnent dans l’environnement de développement. La mise en production exige toujours l’hébergement permanent, l’authentification du site et une sauvegarde testée de sa base privée.
