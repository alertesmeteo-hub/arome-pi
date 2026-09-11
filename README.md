# AROME-PI France 1,3 km

Pipeline GitHub Actions et extension WordPress/Avada indépendants pour le modèle
de prévision immédiate AROME-PI de Météo-France.

## WordPress

Le shortcode exclusif est `[aromepi_meteo]`. Il ne remplace pas et ne déclare
jamais `[arome_meteo]`, réservé au module AROME classique.

## Données

Le workflow lit l'API officielle **Modèle AROME Prévision Immédiate**, produit
les JSON départementaux au schéma v3 partagé avec AROME et publie les cartes et
prévisions dans la branche `data`.

- Résolution : 0,01° (environ 1,3 km)
- Horizon : 0 à 6 heures
- Actualisation : chaque heure, à la minute 27
- Lancement manuel : `workflow_dispatch`
- Secret requis : `METEOFRANCE_API_KEY`

L'API AROME-PI expose surtout les précipitations, rafales et diagnostics de
temps sensible. Les colonnes du schéma v3 qui ne sont pas fournies par cette
API restent à `null` ; elles ne sont jamais remplacées par des valeurs AROME.

Source officielle :
https://www.data.gouv.fr/dataservices/api-modele-arome-prevision-immediate
