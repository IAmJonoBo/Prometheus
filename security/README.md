# Security & governance scaffold

This package hosts the integration points for identity, authorisation, and
secret management. The modules intentionally return `NotImplementedError`
so the scaffolding can exist without pulling heavy dependencies.

- `auth.py` contains helper functions to exchange tokens with Keycloak or other
  OIDC providers.
- `policy.py` wires grant checks through OpenFGA or Oso.
- `secrets.py` establishes a thin Vault client for secret retrieval and
  rotation routines.

Replace the placeholders once credentials, realms, and policy models are
available in your target environment.
