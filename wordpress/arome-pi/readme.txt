=== AROME-PI Météo-France France ===
Contributors: alertesmeteo
Tags: meteo, arome-pi, meteofrance, prevision-immediate, avada
Requires at least: 5.8
Requires PHP: 7.4
Stable tag: 1.0.3
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
