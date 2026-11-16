# Browser account connections (local demo)

Open `http://localhost:4000/`. Normal demo users do not edit `.env` or paste OAuth access tokens. They connect accounts, write one message containing its CTA URL, and publish to any selected connected accounts. The app owner still supplies developer application credentials once.

## Mock mode

`PUBLISH_MODE=mock` enables clearly labelled demo connection buttons. No login page, credentials or external API requests are involved. At least one connected account must be selected. Other platforms are optional. Results say `simulated`, with zero actual posts.

## Owner setup for real mode

Set `APP_BASE_URL` to the exact origin used in the browser, without a trailing path. The local default is `http://localhost:4000`. Use the exact callback below when registering each app. Some providers require HTTPS or restrict development callbacks: configure an accepted HTTPS development origin and matching `APP_BASE_URL` when required. Provider app approval remains mandatory where applicable.

| Provider | Owner environment settings | Callback path | Requested permissions |
|---|---|---|---|
| Facebook | `FACEBOOK_CLIENT_ID`, `FACEBOOK_CLIENT_SECRET` | `/ui/callback/facebook` | `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` |
| LinkedIn | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | `/ui/callback/linkedin` | `openid`, `profile`, `w_member_social` |
| X | `X_CLIENT_ID`, `X_CLIENT_SECRET` | `/ui/callback/x` | `tweet.read`, `tweet.write`, `users.read` |
| Mastodon | `MASTODON_CLIENT_ID`, `MASTODON_CLIENT_SECRET`, `MASTODON_BASE_URL` | `/ui/callback/mastodon` | `read:accounts`, `write:statuses` |
| Bluesky | `BLUESKY_BASE_URL` | No callback in this local flow | User enters their handle and app password in the form |

For example, the local LinkedIn redirect is `http://localhost:4000/ui/callback/linkedin` if accepted by your developer configuration. Enable Share on LinkedIn and OpenID Connect for member posting. Organization author selection is not included in this browser flow. X uses a confidential web application and PKCE S256. Register the Mastodon application on the instance configured by the owner. Bluesky must point at the user's actual PDS.

Set `PUBLISH_MODE=real`, restart, and reload the page. Unconfigured providers show **App setup needed from owner**; they are never represented as connected. OAuth consent happens on the provider website. After Facebook authorization, select an accessible Page. Connecting never posts. The separate publish action confirms the selected destinations in real mode. Unchecked platforms receive no request. The original /posting API still attempts all five platforms for assignment compatibility.

## Session and security boundaries

- Tokens stay in server memory, not localStorage, cookies, source files or `.env`. Only an opaque HttpOnly/SameSite cookie identifies the browser session.
- Sessions last up to eight hours. OAuth states are browser-bound, single-use and expire after ten minutes. Mutation routes require a session CSRF header and reject a mismatched Origin.
- X connections expire with the access token. Reconnect after expiry; no token refresh is implemented.
- Account status responses expose display labels only, never token values. OAuth callback authorization codes are removed from Uvicorn access-log paths.
- UI publishing uses only that session's linked credentials; it does not fall back to owner-level environment access tokens.
- Disconnect forgets the local credential. It does not revoke the provider's grant; revoke it in the provider's own settings when needed.
- Facebook Page selection shows the first 100 accessible Pages. Instance/PDS selection is configured by the owner for this local demo.
- Use one Uvicorn worker on localhost. There is no durable account database, app-user login or production deployment hardening. Existing assignment API routes are still unauthenticated and must not be exposed publicly with owner credentials.

Sources: [LinkedIn OAuth](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow), [X OAuth and PKCE](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code), [Mastodon authorization](https://docs.joinmastodon.org/client/authorized/), [Facebook accounts API](https://developers.facebook.com/docs/graph-api/reference/user/accounts/).
