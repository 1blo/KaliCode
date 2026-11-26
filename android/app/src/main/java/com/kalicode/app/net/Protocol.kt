package com.kalicode.app.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/**
 * The Kali Code wire protocol.
 *
 * The phone is always a *client*: it never executes the agent. It talks to
 * the same `kali/serve.py` WebSocket API that the desktop GUI uses.
 */

@Serializable
data class SessionInfo(
    val id: String = "",
    val title: String = "",
    val cwd: String = "",
    val model: String = "",
    val permissionMode: String = "default",
    val worktree: Boolean = false,
    val created: Double = 0.0,
    val updated: Double = 0.0,
    val archived: Boolean = false,
    val parent: String? = null,
    val status: String = "idle",
    val usage: JsonObject? = null,
    val messageCount: Int = 0,
    val branch: String = "",
)

/** A message received from the server. */
@Serializable
data class ServerMessage(
    val type: String = "",
    val session: String = "",
    val model: String = "",
    val cwd: String = "",
    val version: String = "",
    val sessions: List<SessionInfo> = emptyList(),
    val text: String = "",
    val name: String = "",
    val args: JsonObject? = null,
    val ok: Boolean = true,
    val output: String = "",
    val elapsed: Double = 0.0,
    val reason: String = "",
    val id: String = "",
    val summary: String = "",
    val question: JsonObject? = null,
    val plan: String = "",
    val path: String = "",
    val diff: String = "",
    val message: String = "",
    val usage: JsonObject? = null,
    val description: String = "",
    val final: String = "",
    val background: Boolean = false,
    val server: String = "",
    val count: Int = 0,
    val meta: SessionInfo? = null,
    val tool: String = "",
)

/** A message sent to the server. */
@Serializable
data class ClientMessage(
    val type: String,
    val token: String? = null,
    val session: String? = null,
    val text: String? = null,
    val id: String? = null,
    val answer: String? = null,
    val value: String? = null,
    val model: String? = null,
    val mode: String? = null,
    val title: String? = null,
    val cwd: String? = null,
    val permissionMode: String? = null,
    val worktree: Boolean? = null,
)

object Protocol {
    val json: Json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
        explicitNulls = false
        isLenient = true
    }

    /** Models the server offers. */
    val MODELS = listOf(
        "stepfun-ai/step-5-preview",
        "moonshotai/kimi-k3.1-pro",
        "minimaxai/minimax-m3.1-flash",
    )

    /** Permission modes the app may select (bypass is not offered on mobile). */
    val MODES = listOf(
        "default" to "Manual",
        "acceptEdits" to "Accept edits",
        "plan" to "Plan",
        "auto" to "Auto",
    )

    fun prettyModel(id: String): String =
        id.substringAfterLast('/').replace('-', ' ')

    fun parseJson(text: String): JsonElement? = try {
        json.parseToJsonElement(text)
    } catch (e: Exception) {
        null
    }
}
