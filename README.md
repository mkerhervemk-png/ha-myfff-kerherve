# MyFFF (Portail des Officiels) pour Home Assistant

Intégration non officielle qui remonte dans Home Assistant les **désignations d'un arbitre FFF** :
où et quand il arbitre, à quel poste, à quelle distance, et s'il reste un rapport à saisir.

Elle se connecte avec le compte FFF de l'arbitre (le même que sur `officiels.fff.fr` et dans
l'appli MyFFF) et lit les pages du Portail des Officiels. **Lecture seule : rien n'est modifié sur le portail.**

## Ce que tu obtiens

Un appareil « MyFFF <Prénom> » par compte.

| Entité | Contenu |
| --- | --- |
| Prochaine désignation | Date et heure du prochain match. Attributs : match, équipes, compétition, poste, stade, adresse, distance, type de terrain, officiels, lien vers la fiche, liste `a_venir` |
| Prochain match | « Équipe A - Équipe B » |
| Prochain stade | Nom du stade (adresse en attribut) |
| Distance du prochain match | Kilomètres depuis le domicile (valeur du portail) |
| Désignations à venir | Nombre de matchs à venir |
| Matchs arbitrés cette saison | Nombre de matchs passés (10 derniers en attribut) |
| Dernier match arbitré | Date du dernier match |
| Nouveaux messages | Messages non lus du portail |
| Rapports à saisir | Nombre de rapports « à saisir ou en cours de saisie » |
| Arbitre aujourd'hui (oui/non) | Vrai si un match est prévu aujourd'hui |
| Rapport à saisir (oui/non) | Vrai s'il reste un rapport à faire |
| Calendrier « Arbitrage » | Un événement par match, avec le stade comme lieu |

### Événements (pour les automatisations)

| Événement | Quand |
| --- | --- |
| `myfff_nouvelle_designation` | Une nouvelle désignation apparaît |
| `myfff_designation_modifiee` | L'horaire, le poste ou le stade d'une désignation change |
| `myfff_designation_retiree` | Une désignation à venir disparaît (donnée : `id`) |

Les deux premiers portent les mêmes champs que le capteur « Prochaine désignation »
(`debut`, `match`, `competition`, `poste`, `stade`, `adresse`, `distance_km`, `url`…) plus `officiel` (prénom).
Aucun événement n'est émis au tout premier chargement. Les désignations déjà vues sont mémorisées :
une désignation arrivée pendant un redémarrage est signalée au démarrage suivant.

## Installation (HACS)

1. HACS → menu ⋮ → **Dépôts personnalisés** → `https://github.com/mkerhervemk-png/ha-myfff-kerherve`, type **Intégration**.
2. Télécharge **MyFFF (Portail des Officiels)**, puis redémarre Home Assistant.
3. Paramètres → Appareils et services → **Ajouter une intégration** → **MyFFF**.
4. Saisis l'email et le mot de passe du compte FFF de l'arbitre.

Options (bouton *Configurer*) : fréquence de lecture du portail (6 h par défaut, 1 à 24 h) et
durée d'un match au calendrier (105 min par défaut).

## Exemples d'automatisations

Nouvelle désignation → notification :

```yaml
- alias: "MyFFF — nouvelle désignation"
  triggers:
    - trigger: event
      event_type: myfff_nouvelle_designation
  actions:
    - action: script.ia_notifier
      data:
        urgence: normale
        titre: "⚽ Nouvelle désignation {{ trigger.event.data.officiel }}"
        message: >-
          {{ trigger.event.data.match }} — {{ as_datetime(trigger.event.data.debut).strftime('%d/%m à %Hh%M') }},
          {{ trigger.event.data.stade }} ({{ trigger.event.data.distance_km }} km),
          {{ trigger.event.data.poste }}.
        tag: "myfff_{{ trigger.event.data.id }}"
```

Changement de dernière minute :

```yaml
- alias: "MyFFF — désignation modifiée"
  triggers:
    - trigger: event
      event_type: myfff_designation_modifiee
  actions:
    - action: script.ia_notifier
      data:
        urgence: importante
        titre: "⚠️ Désignation modifiée"
        message: >-
          {{ trigger.event.data.match }} : maintenant
          {{ as_datetime(trigger.event.data.debut).strftime('%d/%m à %Hh%M') }}, {{ trigger.event.data.stade }}.
```

Rappel le matin d'un match (adapte l'identifiant de l'entité à ton prénom) :

```yaml
- alias: "MyFFF — match aujourd'hui"
  triggers:
    - trigger: time
      at: "09:00:00"
  conditions:
    - condition: state
      entity_id: binary_sensor.myfff_ryan_arbitre_aujourd_hui
      state: "on"
  actions:
    - action: script.ia_suggest_batch
      data:
        titre: "⚽ Arbitrage aujourd'hui"
        message: >-
          {{ states('sensor.myfff_ryan_prochain_match') }} à
          {{ as_datetime(states('sensor.myfff_ryan_prochaine_designation')) | as_local | as_timestamp | timestamp_custom('%Hh%M') }},
          {{ states('sensor.myfff_ryan_prochain_stade') }}.
        source: myfff
```

## Limites à connaître

- **Pas d'API officielle.** L'intégration lit des pages web. Si la FFF modifie le portail ou sa page de
  connexion, il faudra adapter `api.py`.
- **Compte d'officiel uniquement.** Un compte FFF sans accès au Portail des Officiels est refusé
  (« ce compte n'a pas accès au Portail des Officiels »).
- **Pas de statistiques joueur.** L'espace « Vestiaires » de l'appli MyFFF n'existe pas sur le web.
- **« Matchs arbitrés cette saison »** compte ce que le portail affiche dans l'historique de la saison en cours.
- **Mot de passe** : il est stocké par Home Assistant, comme pour les autres intégrations à identifiants.

## Dépannage

Journal détaillé, dans `configuration.yaml` :

```yaml
logger:
  logs:
    custom_components.myfff: debug
```

## Tests

```bash
pip install pytest-homeassistant-custom-component
pytest
```

Les tests tournent sur un portail simulé (données fictives) : connexion SSO, lecture des pages,
entités, calendrier, événements, reconnexion après changement de mot de passe.
