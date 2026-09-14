=== AROME-PI Météo-France France ===
Contributors: alertesmeteo
Tags: meteo, arome-pi, meteofrance, prevision-immediate, avada
Requires at least: 5.8
Requires PHP: 7.4
Stable tag: 1.0.15
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Extension WordPress et Avada indépendante pour les prévisions immédiates AROME-PI de Météo-France.

== Description ==

Le shortcode [aromepi_meteo] affiche le module AROME-PI sans modifier ni remplacer le shortcode [arome_meteo] de l'extension AROME classique.

Cette version reprend l'interface du module AROME v1.2.6, avec un espace de noms, des ressources et des réglages propres à AROME-PI. Elle lit les JSON départementaux AROME v3 publiés dans la branche data du dépôt AROME-PI.

AROME-PI est actualisé chaque heure et vise la prévision immédiate jusqu'à 6 heures.

== Installation ==

1. Téléversez le ZIP dans Extensions > Ajouter une extension.
2. Activez AROME-PI Météo-France France.
3. Vérifiez l'adresse des données dans Réglages > AROME-PI Météo-France.
4. Insérez [aromepi_meteo] dans un élément Code ou Shortcode Avada.

== Changelog ==

= 1.0.15 =
* Lecteur d’échéances complet pour les cartes Synoptiques, avec animation et vitesse réglable.
* Menus et commandes conservés en plein écran.
* Échelles de température graduées tous les 2 °C sur Carte France et Synoptique.
* Alerte de fraîcheur corrigée et interface allégée.

= 1.0.14 =
* Cartes synoptiques sans pression superposée, avec accès direct par boutons et échelles fixes.
* Suppression de l’onglet Europe, AROME-PI étant présenté sur la France.
* Frontières départementales vectorielles officielles et rendu des plages météo plus fin au zoom.
* Heures affichées en heure française et signature www.alertes-meteo.com sur les cartes.

= 1.0.13 =
* Projection Lambert conforme pour respecter les proportions de la France.
* Ajout des frontières départementales officielles et des principales villes.
* PNG synoptiques haute définition, affichage sans étirement et zoom limité à la résolution utile.

= 1.0.12 =
* Lissage des champs et isolignes des cartes synoptiques pour supprimer le rendu granuleux.
* Cadrage des cartes synoptiques sur la France métropolitaine et la Corse.

= 1.0.11 =
* Ajout des commandes Capture, Diagramme, Recentrer ville, Plein écran et navigation précédente/suivante dans l’onglet Synoptique.

= 1.0.10 =
* Ajout du zoom sur les cartes synoptiques : boutons, molette, glisser-déplacer, recentrage et plein écran.

= 1.0.9 =
* Remplacement du rendu simulé par de véritables PNG synoptiques générés avec Matplotlib et Cartopy.
* Ajout des isolignes de pression, frontières, palette verticale, run, échéance, validité et signature directement dans chaque image.

= 1.0.8 =
* L’onglet de cartes fixes devient « Synoptique ».
* Ajout d’un menu de cartes et d’un menu d’échéances : une seule grande carte est affichée à la fois.
* Ajout d’un bouton plein écran pour la carte synoptique.

= 1.0.7 =
* Catalogue « Carte en couleur » complété avec toutes les rubriques demandées.
* Nouvelles données directes AROME-PI : neige, graupel, SBCAPE, rafales maximales à 10 m et hauteur de l'isotherme 0 °C.

= 1.0.6 =
* L'onglet « Carte en couleur » reprend la présentation plein cadre du module CEP : run, échéance, légende et signature directement sur la carte.
* Les cartes colorées sont affichées sur une seule colonne pour rester grandes et lisibles.
* Rubriques Température, Précipitations, Vent, Nuages & Humidité, Instabilité et Pression & Géopotentiel.
* Ajout des cartes point de rosée, cumul neige, neige + graupel, cumul de précipitations, rafales maximales à 10 m, SBCAPE et isotherme 0 °C.

= 1.0.5 =
* L'onglet de cartes non interactives est renommé « Carte en couleur ».

= 1.0.4 =
* Carte principale agrandie et zoom initial sur la ville rendu plus lisible.
* Limites départementales affinées puis progressivement atténuées aux grossissements extrêmes.
* Commandes Capture, Diagramme, Recentrer ville et Plein écran réunies au-dessus de la carte.
* Ajout des onglets Carte France, Cartes Europe et Cartes fixes non interactives.
* Libellés simplifiés : Orages et Neige.
* Signature www.alertes-meteo.com seule et renforcée sur les cartes.

= 1.0.3 =
* Limites départementales conservées à tous les niveaux de zoom.
* Compatibilité avec les nouvelles cartes pluie, température, humidité, pression et nuages bas.

= 1.0.2 =
* Source affichée corrigée vers l'API officielle AROME Prévision Immédiate.
* Publication limitée aux champs réellement disponibles ; colonnes absentes conservées à null.

= 1.0.1 =
* Reconstruction complète depuis le module AROME v1.2.6 fourni par l'administrateur.
* Conservation des améliorations d'affichage, de cartes et de cumul de la v1.2.6.

= 1.0.0 =
* Première version autonome du module AROME-PI.
* Shortcode exclusif [aromepi_meteo].
* Espace de noms AMPI/ampi isolé du module AROME AMF/amf.
* Horizon limité aux 6 prochaines heures et contrôle de fraîcheur à 2 heures.
