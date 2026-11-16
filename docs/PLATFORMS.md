# Official API setup and restrictions

Documentation checked on 16 November 2026. API access is account-specific. All five adapters implement real API calls, but **none has been live-tested with user credentials**. HTTP simulation validates request construction and response handling only.

## Facebook Pages

1. Create/configure a Meta developer app for your Page use case.
2. Use Facebook Login and the approved permissions applicable to your app to obtain a **Page access token**, not merely a user token.
3. Confirm the authenticating person has the required Page tasks. The official posting guide lists `pages_manage_posts`, `pages_read_engagement` and other permissions for its broader management operations. Verify which permissions are granted to your token.
4. Set `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_TOKEN` and `FACEBOOK_GRAPH_VERSION` (example: `v27.0`).
5. The adapter posts the full validated text to `/{page-id}/feed`, then requests `permalink_url` for the returned post ID. Missing read access may prevent the permalink lookup without undoing the post.

Development/test-role access differs from serving other users' Pages. App review/advanced permission access may be needed; check the developer dashboard before relying on this integration. This does not post to personal profiles.

Sources: [Meta Page posts guide](https://developers.facebook.com/documentation/pages-api/posts), [Page reference](https://developers.facebook.com/docs/graph-api/reference/page/).

## LinkedIn

1. Create a LinkedIn developer application and obtain the appropriate product access.
2. Obtain an OAuth user access token with `w_member_social` for a member, or `w_organization_social` for an organization where that member has an allowed role.
3. Set `LINKEDIN_AUTHOR_URN` to the actual `urn:li:person:...` or `urn:li:organization:...` identifier from your authorized account setup.
4. Set `LINKEDIN_ACCESS_TOKEN` and a supported `LINKEDIN_API_VERSION` in YYYYMM form; the example uses `202609`.
5. The adapter calls `POST /rest/posts` with the version and Rest.li headers, public visibility, and published lifecycle state.

Permissions and product approval vary by use case. Read access is separate; `r_member_social` is restricted. A successful 201 returns the post URN in `x-restli-id`, which this application preserves. It does not invent a browser permalink. Refresh/re-authorize expired tokens manually.

Sources: [Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-09), [Share on LinkedIn product](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin).

## X (Twitter)

1. Create a developer project/application and enable user authentication.
2. Complete OAuth 2.0 Authorization Code with PKCE for the posting user, requesting `tweet.read`, `tweet.write`, and `users.read`.
3. Store the resulting **user** access token in `X_USER_ACCESS_TOKEN`. An application-only bearer token cannot create posts.
4. Ensure your developer account has the needed endpoint access and available credits. Current official documentation describes pay-per-use billing; check the console for current cost, particularly posts containing URLs.
5. The adapter calls `POST https://api.x.com/2/tweets` and constructs a status link only from a returned numeric post ID.

OAuth 1.0a is supported by X, but this application implements OAuth 2.0 user tokens only. Account visibility and X's weighted text limits may differ from the assignment's 200-code-point rule. API failures are reported; public access is not assumed.

Sources: [Create post](https://docs.x.com/x-api/posts/create-post), [Authentication mapping](https://docs.x.com/fundamentals/authentication/guides/v2-authentication-mapping), [API pricing](https://docs.x.com/x-api/getting-started/pricing).

## Mastodon

1. Sign in to an account on your chosen instance.
2. Create an application/access token through that instance's developer settings, granting `write:statuses`.
3. Set `MASTODON_BASE_URL` to its HTTPS origin and `MASTODON_TOKEN` to the token.
4. The adapter calls `POST /api/v1/statuses` with the complete text and requested `public` visibility. It preserves the returned ID and URL.

Instance policies, account state and moderation can affect publication. Requested public visibility does not prove anonymous accessibility; the response keeps public access unknown.

Source: [Mastodon statuses API](https://docs.joinmastodon.org/methods/statuses/).

## Bluesky

1. Use an existing Bluesky account and generate an app password in its account settings.
2. Set `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, and the account's actual personal data server in `BLUESKY_BASE_URL`.
3. The default `https://bsky.social` is intended for accounts hosted there. For another PDS, set the correct HTTPS origin manually.
4. The adapter obtains a session using `com.atproto.server.createSession`, then calls `com.atproto.repo.createRecord` for `app.bsky.feed.post`.
5. The CTA facet uses UTF-8 byte offsets, including when the message contains emoji. A browser link is derived only from the returned record URI.

A new session is created per request for simplicity. The service does not discover a migrated PDS or maintain/refresh sessions. An app-password flow suits this local single-account practical; broader multi-user products require a separate authentication design.

Source: [Official post creation guide](https://docs.bsky.app/docs/tutorials/creating-a-post).
