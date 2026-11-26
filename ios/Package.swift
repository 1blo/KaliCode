// swift-tools-version: 5.9
//
// Package.swift - the Kali Code iOS app.
//
// The app is a SwiftUI client for the same Kali Code server the desktop
// GUI and the Android app talk to. It has no third-party dependencies:
// the WebSocket client is URLSessionWebSocketTask and the JSON layer is
// Foundation's Codable.
//
// Build it from the command line with:
//
//     swift build -c release
//
// or open the folder in Xcode (File > Open) and run it on a device or a
// simulator. The Xcode project in KaliCode.xcodeproj is preconfigured for
// the same bundle identifier as the Android app.
//
// Requires iOS 16.0 or later (the app uses NavigationStack, Charts-free
// SwiftUI and the async/await WebSocket APIs).

import PackageDescription

let package = Package(
    name: "KaliCode",
    platforms: [
        .iOS(.v16),
        .macOS(.v13),
    ],
    products: [
        .library(name: "KaliCodeKit", targets: ["KaliCodeKit"]),
        .executable(name: "KaliCode", targets: ["KaliCode"]),
    ],
    targets: [
        // The reusable client: protocol, transport, state.
        .target(
            name: "KaliCodeKit",
            path: "Sources/KaliCodeKit"
        ),
        // The SwiftUI application.
        .executableTarget(
            name: "KaliCode",
            dependencies: ["KaliCodeKit"],
            path: "Sources/KaliCode"
        ),
        .testTarget(
            name: "KaliCodeKitTests",
            dependencies: ["KaliCodeKit"],
            path: "Tests/KaliCodeKitTests"
        ),
    ]
)
