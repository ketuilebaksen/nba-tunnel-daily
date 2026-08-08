# nba-tunnel-daily

Automated daily Knicks **storytelling** videos for the **NBA Tunnel** channel.

Sister project of `knicks-auto-daily` (daily news). Same engine, different
editorial identity — configured entirely in `channel.json`:

| | Ketuil KNICKS | NBA Tunnel |
|---|---|---|
| Editorial | today's news, rumours, games | evergreen stories, history, analysis |
| Pace | fast cuts (2.8 / 3.4 s) | slow cuts (4.2 / 6.5 s) |
| Overlays | speech, chat, comic, lower-third, bounce | lower-third + speech only, gentle slide |
| Voice | Alex Smooth / US voices | UK documentary voices |
| Thumbnail | fiery arena, hype words | dark editorial, calm words |
| Clip order | offset 37 | offset 91 (never the same scenes) |

Setup: see the parent project's README. Required secrets are identical, but
`YT_CLIENT_ID` / `YT_CLIENT_SECRET` / `YT_REFRESH_TOKEN` must be authorised for
the **NBA Tunnel** channel.
