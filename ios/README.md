# Kali Code for iOS

The native iOS client for Kali Code — the same agentic coding CLI, with a
SwiftUI interface.

The phone is always a **client**. The agent, its tools and your permissions
always run on the server (`kali/serve.py`), so the app works from anywhere
and the server can be a free-tier Render host.

## What it does

| | |
|---|---|
| Streaming chat | the assistant's output arrives token by token |
| Tool cards | every tool call, with its output, collapsible |
| Permission prompts | allow / always / deny, right in the conversation |
| Question prompts | the agent's `AskUserQuestion` with its options |
| Plan approval | approve or reject a plan before it is executed |
| Model picker | switch between the three models the server offers |
| Permission mode | Manual, Accept edits, Plan, Auto |
| Session list | every session on the server, switch between them |
| Context usage | the percentage of the context window in use |
| Interrupt | stop a running turn |
| Auto-reconnect | reconnects with a backoff when the link drops |

## Build it

You need a Mac, Xcode 15 or newer and an Apple Developer account.

```bash
git clone https://github.com/1blo/KaliCode
cd KaliCode/ios
open KaliCode.xcodeproj
```

1. Select the **KaliCode** target.
2. Go to **Signing & Capabilities**, pick your team. If `com.kalicode.app`
   is taken, change the bundle id.
3. Choose a device or a simulator and press **Run**.

### From the command line

```bash
cd ios
xcodebuild -project KaliCode.xcodeproj -scheme KaliCode \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -allowProvisioningUpdates \
  build
```

### Swift Package Manager

The client is also a SwiftPM package, so you can drop it into another
app:

```swift
.package(url: "https://github.com/1blo/KaliCode.git", from: "1.2.0")
```

and depend on the `KaliCodeKit` product.

## Connect

Start the server:

```bash
kali serve --host 0.0.0.0 --port 8000
```

It prints an access token. Put the server's public URL and that token into
the app's connect screen; both are remembered, so the app reconnects by
itself the next time it opens.

The desktop app writes the same values to
`~/Library/Application Support/KaliCode/desktop.json`.

## Tests

```bash
cd ios
swift test
```

## Project layout

```
ios/
  Package.swift                       the SwiftPM manifest (iOS 16+)
  KaliCode.xcodeproj/                 the Xcode project + the shared scheme
  Sources/
    KaliCodeKit/
      Protocol.swift                  the wire protocol (Codable)
      KaliClient.swift                the WebSocket transport
      KaliStore.swift                 the state machine
      Theme.swift                     the shared palette
    KaliCode/
      KaliApp.swift                   the SwiftUI views
  Resources/
    Info.plist                        ATS exception, scene manifest
    KaliCode.entitlements             push notifications
    Assets.xcassets/                  the app icon + the launch colour
  Tests/
    KaliCodeKitTests/                 the protocol tests
```

The Xcode project is generated rather than hand-written, so it never
drifts from the source files:

```bash
python tools/build_ios_project.py     # regenerate ios/KaliCode.xcodeproj
python tools/make_ios_icons.py        # regenerate the app icon
```

## The other iOS client

If you do not want to build anything, open the server URL in Safari and
tap **Share → Add to Home Screen**. That installs the PWA as a standalone
app — see the iOS section of the [main README](../README.md#ios-app) for
what it does and how it differs.
