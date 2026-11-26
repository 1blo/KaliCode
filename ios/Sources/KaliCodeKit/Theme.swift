// Theme.swift - the colours and metrics of the Kali Code iOS app.
//
// The palette matches the desktop GUI and the Android app so the three
// clients look like the same product.

import SwiftUI

public enum Theme {
    // MARK: Colours

    public static let bg = Color(hex: 0x0D0D12)
    public static let panel = Color(hex: 0x16161E)
    public static let panel2 = Color(hex: 0x1E1E28)
    public static let panel3 = Color(hex: 0x2A2A36)
    public static let border = Color(hex: 0x2A2A36)
    public static let fg = Color(hex: 0xE8E8EF)
    public static let dim = Color(hex: 0x8B8B9E)
    public static let dimmer = Color(hex: 0x5E5E70)
    public static let accent = Color(hex: 0xB14AFF)
    public static let accent2 = Color(hex: 0xD18BFF)
    public static let purple = Color(hex: 0xD18BFF)
    public static let blue = Color(hex: 0x5EA0FF)
    public static let green = Color(hex: 0x3DDC84)
    public static let yellow = Color(hex: 0xFFB648)
    public static let red = Color(hex: 0xFF5F56)

    // MARK: Metrics

    public static let corner: CGFloat = 12
    public static let smallCorner: CGFloat = 8
}

extension Color {
    /// Build a colour from a 24-bit RGB value.
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0,
            opacity: 1
        )
    }
}
