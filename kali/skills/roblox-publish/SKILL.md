---
name: roblox-publish
description: Build and publish a Roblox game from a Rojo project using the Open Cloud Place Publishing API, without Roblox Studio. Use when the user asks to publish, deploy, release, or ship a Roblox game or experience, or asks to turn Luau source into a live Roblox place.
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, RobloxPublish, RobloxStatus, TaskCreate, TaskUpdate
---

# Roblox publishing

Publish a Roblox experience headlessly: Rojo builds the place file, the Open
Cloud API uploads and publishes it. No Roblox Studio required.

## Project layout

A Rojo project has a `default.project.json` at its root mapping source files
to the instance tree:

```json
{
  "name": "MyGame",
  "tree": {
    "$className": "DataModel",
    "ReplicatedStorage": {
      "$className": "ReplicatedStorage",
      "Shared": { "$path": "src/shared" }
    },
    "ServerScriptService": {
      "$className": "ServerScriptService",
      "Server": { "$path": "src/server" }
    },
    "StarterPlayer": {
      "$className": "StarterPlayer",
      "StarterPlayerScripts": {
        "$className": "StarterPlayerScripts",
        "Client": { "$path": "src/client" }
      }
    }
  }
}
```

- `.luau` / `.lua` files become `Script` instances.
- `.server.lua` becomes a `Script` (server only).
- `.client.lua` becomes a `LocalScript` (client only).
- `.model.json` files describe non-script instances (parts, folders, etc.).
- A directory maps to a `Folder` unless a sibling `.model.json` overrides it.

## Publishing

1. **Check the setup first** — call `RobloxStatus`. It reports whether the API
   key, universe ID, place ID, Rojo binary and project file are all present.
   If something is missing, tell the user exactly which one and stop. Do not
   attempt to work around a missing credential.

2. **Make the changes** in the source tree (`src/`, `default.project.json`).
   Edit Luau source, not place files.

3. **Commit** your work. `RobloxPublish` commits and pushes by default, but
   commit explicitly with Bash when you want a meaningful message:

   ```bash
   git add -A && git commit -m "feat: add tycoon loop" && git push
   ```

4. **Publish** with `RobloxPublish`. It runs `rojo build` to produce
   `build.rbxl`, uploads it, and returns the new version number and the game
   link.

   - `saved_only: true` saves the version without making it live.
   - `commit: false` skips the git commit if you already committed.

## Constraints and gotchas

- **Use binary `.rbxl`, not `.rbxlx`.** Open Cloud currently drops the default
  server-authoritative character controls when publishing from an `.rbxlx`
  file. `RobloxPublish` builds binary first and only falls back to XML if the
  binary build fails.
- **Publish limits.** Roblox allows roughly 5 *new* public games per day per
  account, and the Place Publishing API returns HTTP 409 when a limit is hit.
  Updates to an already-public game are not affected the same way.
- **10 MiB** is the maximum place file size.
- **Some instance types do not round-trip through the API**: `EditableImage`,
  `EditableMesh`, `PartOperation`, `SurfaceAppearance`, `BaseWrap`. If the
  place uses these, it must be published from Studio instead.
- **Server-authoritative movement** must be set up in the source (the
  `Player` character's `Humanoid` + `Animate` script), not by relying on
  Studio defaults, or players will not be able to move.

## Credentials

Read from the environment (never hardcode, never commit):

- `ROBLOX_API_KEY` — Open Cloud API key with the `universe-places:write` scope
- `ROBLOX_UNIVERSE_ID` — the experience's universe id
- `ROBLOX_PLACE_ID` — the place id to publish to
- `ROBLOX_PROJECT_DIR` — Rojo project root (defaults to the workspace)

The API key must be granted access to the specific experience in
Creator Dashboard → API Keys → Access Permissions, with Read and Write.

## Verifying a publish

After a successful publish, report the version number and link to the user.
If the game should now be visible in the Creator Dashboard, tell them where to
look: Dashboard → Creations → the experience → Places → version history.
