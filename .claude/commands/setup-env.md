---
description: Set up your course API key and endpoints in .env, without the key ever passing through Claude.
---

Help the user fill in the course endpoint settings in their `.env`. The key and host must **never** pass through this chat.

**Rules (no exceptions):**
- Never ask for the API key or the course host. Never read, print, or edit `.env` (CLAUDE.md §8).
- If the user pastes a key, host, or the course endpoint list into the chat anyway: don't repeat any of it, don't write it to any file, and tell them plainly that anything typed into the chat is sent to the model and kept in the conversation history. Then continue with the steps below. If it was a key, tell them to mention it to the PM.
- Don't run `npm run env:setup` or `npm run env:import` yourself. It only works in the user's own terminal and refuses to run from Claude, on purpose.

**Steps to give the user**, in plain English, one at a time:

1. Have the course endpoint list open (from the course materials). You'll need two things from it: the **host** (the part after `http://` and before the `:`) and the **API key**.
2. Open your own terminal window. The `!` prefix in Claude Code can't answer questions, so it won't work here.
   - Mac: Terminal, or in VS Code: **Terminal → New Terminal**
   - Windows: PowerShell, or in VS Code: **Terminal → New Terminal**
3. Make sure you're in the project folder (VS Code's terminal already is), then run: `npm run env:setup`
4. Answer the two questions. The key is **hidden while you type or paste it**, so press Enter even though nothing appears. If your `.env` already has course settings, it asks before replacing them.
5. It saves `.env` (only your user account can read it), sets `PROVIDER_MODE=live`, and shows a check that lists each setting as `ok` without showing any values.

**Option B (applies every setting from the list at once):** have the user save the course endpoint list, exactly as published, to a text file **outside the project folder** (e.g. Documents). In their own terminal, they run `npm run env:import`, drag the file into the window and press Enter. It reads the host, key, ports and models, names any missing or skipped services (by name only), and refuses a file inside the project. Suggest they keep that file somewhere private.

**Afterwards:** run `npm run env:check` yourself to confirm. It never shows values. If any line isn't `ok`, help by variable **name** only. A wrong host or key means running `npm run env:setup` again. Ports and model names come from the script with `env:setup`; with `env:import` they come from the list file, so a new course list is just a re-import.
