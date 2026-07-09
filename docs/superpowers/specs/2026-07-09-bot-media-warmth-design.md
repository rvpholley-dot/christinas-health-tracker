# Bot media handling & warmth — design

**Date:** 2026-07-09
**Status:** Approved by Brian (this session)
**Problem:** Christina sends the bot photos and off-topic messages. Today a
photo gets the canned "I can read texts and voice memos" reply, its caption
is dropped, and the file is lost. Brian wants no scope-policing — the bot
should stay warm — and nothing she shares should vanish. Chosen approach:
give the bot vision so its warmth is genuine, and save every file.

## Goals

- Photos: the bot actually sees them (the model supports vision), responds
  genuinely, and logs from them when they are clearly health content
  (patches on skin, a scale readout, a supplement bottle).
- Every photo/video/document she sends is saved to a dated inbox folder,
  whether or not the bot understood it.
- Off-topic text gets a short, warm, natural reply — never a lecture about
  scope. Lasting personal facts go to `remember`.

## Non-goals

- No video/audio understanding (saved only; voice memos keep the existing
  transcription path).
- No gallery/browsing UI. The inbox is a folder Brian checks.

## Telegram loop (`agent/telegram_loop.py`)

`_handle_update` grows a media branch (allowlisted chats only):

- `message.photo`: Telegram sends multiple sizes; take the largest with
  `file_size` ≤ ~4 MB (next smaller otherwise). Download via the existing
  `getFile` pattern (same as voice). Save it. Pass it to the agent as an
  image, with `message.caption` as the text (caption may be empty).
- `message.video` / `message.document` / `message.audio` / `message.sticker`:
  download (skip and apologize gracefully if > 20 MB — Telegram's getFile
  cap), save, and pass the agent a text stand-in:
  `(Christina sent a video — it's saved for Brian to see. Respond warmly.)`
  plus any caption.
- Saving: `inbox_dir` config key, default `D:\Christina\cht-agent\inbox`,
  file at `<inbox_dir>\YYYY-MM-DD\HHMMSS-<kind><ext>` (ext from Telegram's
  `file_path`). Save failures are logged, never surfaced to her.
- The catch-all reply ("I can read texts and voice memos…") remains only for
  truly empty messages (e.g., a contact card), reworded kindly.

## Agent (`agent/agent_llm.py`)

- `handle_message(config, chat_id, text, images=None)` — `images` is a list
  of `{media_type, data}` (base64). Images are sent as image blocks in the
  new user turn only; conversation history stores a text placeholder
  (`[photo saved: <path>] <caption>`) since history replays as text.
- System prompt additions:
  - She may send photos; if one clearly shows loggable health content, offer
    to log it (or log it when unambiguous, e.g., a scale reading) — the
    existing grounding rules apply (log_entry or it didn't happen).
  - Off-topic messages: respond warmly and briefly, like a friend would.
    NEVER say something is outside your scope or function. If she shares
    something personal and lasting, use `remember`.
- The no-tools grounding guard from 2026-07-09 applies unchanged.

## Deploy

Agent-side only: restart cht-agent. No app or Pages deploy.

## Testing

- Unit: media-save helper with a stubbed download (path shape, size
  fallback, unknown extension).
- Live: Brian sends the bot a photo with a caption from his own allowlisted
  Telegram; verify the file lands in the inbox, the reply reflects the photo
  content, and the conversation history stores the placeholder.

## Risks

- Vision misreads a photo and logs something wrong: mitigated by preferring
  "offer to log" over silent logging except for unambiguous cases; every
  log confirmation states what was logged so she can correct it.
- Inbox growth: photos are small (Telegram-compressed); revisit if the
  folder ever matters.
