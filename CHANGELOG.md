# Journal des modifications

## 0.2.0 — diagnostic de sécurité et cycle de session

- Distingue un HTTP 403 de sécurité d'un refus d'identifiants.
- Récupère l'en-tête `x-reference-error` pour faciliter une demande au support FFF.
- N'expose plus un extrait de la page HTML de blocage dans les journaux.
- Affiche un message de configuration explicite pour le HTTP 403.
- Formalise un état de session en mémoire, confirmé uniquement après lecture réussie d’une page protégée.
- Conserve la reconnexion existante lorsque le portail renvoie le formulaire SSO : les identifiants déjà enregistrés sont réutilisés et les cookies restent gérés par la session du client.
- Ajoute un test simulé vérifiant la classification du 403 et la conservation de sa référence.

Limite connue : cette version ne contourne pas les protections du portail et ne peut pas rendre accessible un endpoint qui répond HTTP 403. Une validation réelle de la connexion dépend d'un accès automatisé autorisé par la FFF.
