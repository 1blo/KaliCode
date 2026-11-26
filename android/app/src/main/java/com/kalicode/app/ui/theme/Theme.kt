package com.kalicode.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Bg = Color(0xFF141413)
val Panel = Color(0xFF1C1C1A)
val Panel2 = Color(0xFF232321)
val Panel3 = Color(0xFF2B2B28)
val Border = Color(0xFF32322E)
val Fg = Color(0xFFE8E6E1)
val Dim = Color(0xFF9A968C)
val Dimmer = Color(0xFF6F6C65)
val Accent = Color(0xFFD97757)
val Accent2 = Color(0xFFC96442)
val Green = Color(0xFF7FB069)
val Blue = Color(0xFF6A9FB5)
val Red = Color(0xFFCC6655)
val Yellow = Color(0xFFD4A24C)
val Purple = Color(0xFFA78BBA)

private val Scheme = darkColorScheme(
    primary = Accent,
    onPrimary = Color(0xFF17140F),
    secondary = Blue,
    background = Bg,
    onBackground = Fg,
    surface = Panel,
    onSurface = Fg,
    surfaceVariant = Panel2,
    onSurfaceVariant = Dim,
    outline = Border,
    error = Red,
)

@Composable
fun KaliTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    // Kali Code always uses the dark palette - the desktop app does too.
    MaterialTheme(
        colorScheme = Scheme,
        typography = androidx.compose.material3.Typography(),
        content = content,
    )
}
