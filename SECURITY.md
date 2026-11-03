# Politique de sécurité

## Versions suivies

Seule la branche `main` à partir du dernier commit dont la CI réussit est
actuellement suivie. Aucune version de production n'est encore publiée.

## Signaler une vulnérabilité

Utilisez le signalement privé GitHub dans l'onglet **Security** du dépôt. Ne
créez pas d'issue publique et ne joignez aucun secret, jeton, mot de passe ou
contenu appartenant à un client.

Le signalement doit contenir une description, les préconditions, l'impact
possible et une reproduction minimale utilisant uniquement des données
fictives. La réception d'un signalement ne constitue pas un engagement de délai
tant qu'un contrat de maintenance et une procédure d'incident ne sont pas
formalisés.

## Double authentification administrateur

Les comptes `admin` et `super_admin` peuvent activer une double authentification
TOTP (RFC 6238, SHA-1, 6 chiffres, pas de 30 secondes) depuis **Paramètres >
Double authentification**. Le mot de passe seul ne pose plus de cookie de
session : un défi signé, valable 5 minutes, est échangé contre un code TOTP ou
un code de secours à usage unique.

- Le secret TOTP est stocké dans le document utilisateur ; il n'est jamais
  renvoyé par `/auth/me`.
- Les codes de secours sont hachés (bcrypt + pré-hachage SHA-256) et affichés
  une seule fois.
- Les échecs sont limités par compte et par source, comme la connexion.
- Les réponses contenant un secret ou des codes sont marquées `Cache-Control:
  no-store`.
- La désactivation exige le mot de passe **et** un code TOTP ou de secours.

Limites : pas encore de QR code intégré, pas de clé matérielle, pas de
réinitialisation centralisée par le super-admin, et aucun test avec une
application d'authentification réelle n'a été exécuté.

## Limites actuelles

KYLOT est candidat à une préproduction contrôlée. MongoDB réel, Stripe sandbox,
emails, IA, concurrence multi-processus, sauvegarde/restauration et proxy final
doivent encore être validés avant une ouverture commerciale.
