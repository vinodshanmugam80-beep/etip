# SSO (OIDC single sign-on) — Examples

**ETIP 2.0.** Per-tenant OpenID Connect. Configuring SSO requires `sso:manage`
(Org Admin). Users then sign in through the organization's identity provider
(Okta, Azure AD, Google, Keycloak, …); ETIP verifies the ID token and issues its
own session tokens, provisioning the user just-in-time on first login.

`BASE = http://localhost:8000/api/v1`.

## 1. Configure the IdP (admin, once)
`PUT /auth/sso/config` (`sso:manage`)
```json
{ "client_id": "…", "client_secret": "…", "issuer": "https://your-idp/",
  "authorize_url": "https://your-idp/authorize", "token_url": "https://your-idp/token",
  "jwks_url": "https://your-idp/jwks", "default_role_name": "Member",
  "allowed_domains": ["yourcompany.com"], "is_enabled": true }
```
The **client secret is never returned** — `GET /auth/sso/config` shows `secret_set`
only, and a `PUT` that omits the secret keeps the stored one. Register ETIP's
callback with your IdP: `{PUBLIC_BASE_URL}/api/v1/auth/sso/callback`.

## 2. Sign in
- `GET /auth/sso/login?organization_slug=your-org` → returns the IdP `authorize_url`
  (with signed `state` + `nonce`). Redirect the user there.
- The IdP redirects back to `GET /auth/sso/callback?code=…&state=…`. ETIP exchanges
  the code, verifies the ID token (signature via JWKS, audience, issuer, nonce),
  provisions the user (assigning `default_role_name`, enforcing `allowed_domains`),
  and returns an ETIP **access + refresh token** pair.

## Security & scope
- Multi-tenant: each org configures its own IdP; the tenant is bound into the
  signed `state`, so the callback never crosses tenants.
- Standard OIDC authorization-code flow with a confidential client; state is a
  short-lived signed JWT (no server session store).
- **Honest caveat:** the code-exchange + JWKS verification step is covered by
  tests via a mock; final validation should be done against your real IdP in a
  staging environment. Set `PUBLIC_BASE_URL` so callback URLs are correct.
