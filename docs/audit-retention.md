# Journal d’audit — minimisation et rétention

## Rétention

```text
AUDIT_RETENTION_DAYS=365
```

Le champ `at_dt` est indexé avec un TTL MongoDB de 365 jours.

Les anciens enregistrements qui ne possèdent pas `at_dt` ne sont pas supprimés
automatiquement : une purge/migration explicite doit être planifiée.

## Minimisation

`log_audit` ne recopie plus les snapshots métier complets.

Sont masqués :

```text
password, password_hash
mfa_secret, mfa_pending_secret
mfa_recovery_codes
access_token, refresh_token, token
client_secret, authorization, cookie
contenu des photos
```

Les chaînes sont limitées à 500 caractères, les listes à 50 éléments et la
profondeur à 5 niveaux.

## Limites

```text
le journal reste best-effort
les actions critiques stock ne sont pas encore transactionnelles (F-05)
la purge des anciens documents sans at_dt reste à planifier
```
