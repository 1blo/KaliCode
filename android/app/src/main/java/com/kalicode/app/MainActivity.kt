package com.kalicode.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import com.kalicode.app.ui.KaliApp
import com.kalicode.app.ui.theme.KaliTheme

class MainActivity : ComponentActivity() {
    private val vm: KaliViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            KaliTheme {
                KaliApp(vm)
            }
        }
    }
}
