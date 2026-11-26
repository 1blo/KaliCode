package com.kalicode.app.ui

/** One entry in the conversation. */
sealed class ChatItem {
    data class User(val text: String) : ChatItem()
    data class Assistant(val text: String) : ChatItem()
    data class Thinking(val text: String) : ChatItem()
    data class Error(val text: String) : ChatItem()
    data class Tool(val name: String, val summary: String, val output: String = "") : ChatItem()
    data class Plan(val text: String) : ChatItem()

    data class ToolItem(
        val name: String,
        val summary: String,
        val done: Boolean = false,
        val ok: Boolean = true,
        val elapsed: Double = 0.0,
        val output: String = "",
    ) : ChatItem()
}

/** A permission prompt awaiting an answer. */
data class PermissionRequest(
    val id: String,
    val tool: String,
    val summary: String,
)

/** An AskUserQuestion prompt awaiting an answer. */
data class QuestionRequest(
    val id: String,
    val text: String,
    val options: List<String>,
)

/** A plan awaiting approval. */
data class PlanRequest(
    val id: String,
    val plan: String,
)
