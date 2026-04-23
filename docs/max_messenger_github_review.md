# MAX Messenger GitHub Review

Date captured: 2026-04-21

Organization: `https://github.com/max-messenger`

## What MAX provides officially

- `max-bot-api-client-go`
  Official Go Bot API client. Actively updated and includes `docs`, `examples`, `schemes`, `keyboard.go`, `messages.go`, and `subscriptions.go`.
- `max-bot-api-client-ts`
  Official TypeScript Bot API client. Useful as a reference for request/response models and payload formats.
- `max-botapi-python`
  Public Python repository, but it is a maintained fork of `love-apples/maxapi` that MAX has checked and published.
- `max-ui`
  TypeScript UI library/SDK, more relevant for app integrations and richer MAX interfaces than for our polling bot.

## What this means for our project

- MAX already exposes the core Bot API surface we need: polling, webhook, messages, inline buttons, subscriptions, and uploads.
- For Python there is a public MAX-backed library path if we want to move from our thin client to a fuller SDK later.
- The strongest current reference implementation is the Go client because it is actively maintained and documents more of the API surface.

## What helps us right now

- The shape of inline buttons and callback flows is confirmed by official MAX client libraries.
- Both polling and webhook are supported, so we can move off long polling later without redesigning product flows.
- The public repos support our current product assumptions around:
  - `bot_started`
  - message events
  - callback buttons
  - membership/subscription checks

## What is still unclear

- I did not find clear public evidence in the `max-messenger` repos for a guaranteed bot-side deep-link pattern equivalent to Telegram's direct `t.me/...` chat open behavior.
- Because of that, the safe interpretation is:
  - if we have a direct profile/chat link that the MAX client understands, we can try it as a `link` button;
  - if the client does not open the chat from that link, we keep a fallback contact path.

## What is fixed in our project now

- Telegram manager button now opens the manager chat directly:
  - `https://t.me/adkcosmetics`
- MAX manager button now tries to open the chat directly via deep link:
  - `max://max.ru/u/f9LHodD0cOIJgI1mtlCcMCXlLn0ey0DuDWwbXaDEfcKeWxl5I6wL7-Uzc5Y`
- MAX fallback contact is preserved in code for already-sent legacy callback buttons:
  - `+79132003939`

## Practical recommendation

- Telegram: direct URL button is the right approach and is already applied.
- MAX: test the current `max://...` deep link in the real MAX client.
- If the MAX client does not open the target chat correctly, keep the fallback manager contact flow and switch the product copy to guide the user explicitly.

## Links

- Org: `https://github.com/max-messenger`
- Go client: `https://github.com/max-messenger/max-bot-api-client-go`
- Python client: `https://github.com/max-messenger/max-botapi-python`
- TypeScript client: `https://github.com/max-messenger/max-bot-api-client-ts`
