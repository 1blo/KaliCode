package com.kalicode.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.kalicode.app.net.ClientMessage
import com.kalicode.app.net.KaliClient
import com.kalicode.app.net.Protocol
import com.kalicode.app.net.ServerMessage
import com.kalicode.app.net.SessionInfo
import com.kalicode.app.ui.ChatItem
import com.kalicode.app.ui.PermissionRequest
import com.kalicode.app.ui.PlanRequest
import com.kalicode.app.ui.QuestionRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** The whole UI state in one place. */
data class KaliState(
    val serverUrl: String = "",
    val token: String = "",
    val connected: Boolean = false,
    val status: KaliClient.Status = KaliClient.Status.Disconnected,
    val sessions: List<SessionInfo> = emptyList(),
    val currentSession: String? = null,
    val chat: List<ChatItem> = emptyList(),
    val busy: Boolean = false,
    val model: String = Protocol.MODELS.first(),
    val permissionMode: String = "default",
    val cwd: String = "",
    val contextPercent: Int = 0,
    val error: String? = null,
    val showArchived: Boolean = false,
)

class KaliViewModel(app: Application) : AndroidViewModel(app) {
    private val client = KaliClient(viewModelScope)

    private val _state = MutableStateFlow(KaliState())
    val state: StateFlow<KaliState> = _state

    /** Permission prompts waiting for an answer. */
    private val _permissions = MutableStateFlow<List<PermissionRequest>>(emptyList())
    val permissions: StateFlow<List<PermissionRequest>> = _permissions

    private val _questions = MutableStateFlow<List<QuestionRequest>>(emptyList())
    val questions: StateFlow<List<QuestionRequest>> = _questions

    private val _plans = MutableStateFlow<List<PlanRequest>>(emptyList())
    val plans: StateFlow<List<PlanRequest>> = _plans

    private val _lastUsage = MutableStateFlow<Int>(0)
    val lastUsage: StateFlow<Int> = _lastUsage

    init {
        viewModelScope.launch {
            client.events.collect { handle(it) }
        }
    }

    // ------------------------------------------------------------- connect
    fun connect(serverUrl: String, token: String, resumeSession: String? = null) {
        _state.value = _state.value.copy(
            serverUrl = serverUrl,
            token = token,
            error = null,
        )
        client.connect(serverUrl, token, resumeSession)
    }

    fun disconnect() {
        client.disconnect()
        _state.value = _state.value.copy(connected = false, status = KaliClient.Status.Disconnected)
    }

    fun reconnect() = client.reconnectNow()

    fun clearError() {
        _state.value = _state.value.copy(error = null)
    }

    // ------------------------------------------------------------ messages
    fun sendPrompt(text: String) {
        val clean = text.trim()
        if (clean.isEmpty() || _state.value.busy) return
        _state.value = _state.value.copy(
            chat = _state.value.chat + ChatItem.User(clean),
            busy = true,
        )
        client.prompt(clean)
    }

    fun interrupt() {
        client.interrupt()
        _state.value = _state.value.copy(busy = false)
    }

    fun answerPermission(id: String, answer: String) {
        client.reply(id, answer)
        _permissions.value = _permissions.value.filterNot { it.id == id }
    }

    fun answerQuestion(id: String, value: String) {
        client.answer(id, value)
        _questions.value = _questions.value.filterNot { it.id == id }
    }

    fun answerPlan(id: String, answer: String) {
        client.reply(id, answer)
        _plans.value = _plans.value.filterNot { it.id == id }
    }

    fun newSession() = client.newSession()
    fun switchSession(id: String) = client.switchSession(id)
    fun setModel(model: String) {
        _state.value = _state.value.copy(model = model)
        client.setModel(model)
    }
    fun setMode(mode: String) {
        _state.value = _state.value.copy(permissionMode = mode)
        client.setMode(mode)
    }
    fun rename(title: String) = client.rename(title)
    fun toggleArchived() {
        _state.value = _state.value.copy(showArchived = !_state.value.showArchived)
    }

    fun clearChat() {
        _state.value = _state.value.copy(chat = emptyList())
    }

    // -------------------------------------------------------------- events
    private fun handle(msg: ServerMessage) {
        val s = _state.value

        when (msg.type) {
            "ready" -> {
                _state.value = s.copy(
                    connected = true,
                    status = KaliClient.Status.Connected,
                    currentSession = msg.session.ifEmpty { s.currentSession },
                    sessions = msg.sessions.ifEmpty { s.sessions },
                    cwd = msg.cwd.ifEmpty { s.cwd },
                    model = msg.model.ifEmpty { s.model },
                    busy = false,
                    error = null,
                )
            }

            "sessions" -> {
                _state.value = s.copy(sessions = msg.sessions)
            }

            "session_meta" -> {
                val meta = msg.meta
                if (meta != null) {
                    _state.value = s.copy(
                        sessions = s.sessions.map { if (it.id == meta.id) meta else it },
                        model = meta.model,
                        permissionMode = meta.permissionMode,
                        cwd = meta.cwd,
                    )
                }
            }

            "thinking" -> {
                if (msg.text.isNotBlank()) appendText(ChatItem.Thinking(msg.text))
            }

            "text" -> {
                appendText(ChatItem.Assistant(msg.text))
            }

            "tool_start" -> {
                val item = ChatItem.ToolItem(name = msg.name, summary = msg.summary)
                _state.value = _state.value.copy(chat = _state.value.chat + item)
            }

            "tool_result" -> {
                _state.value = _state.value.copy(
                    chat = _state.value.chat.map {
                        if (it is ChatItem.ToolItem && it.name == msg.name && !it.done) {
                            it.copy(done = true, ok = msg.ok, elapsed = msg.elapsed, output = msg.output)
                        } else {
                            it
                        }
                    }
                )
            }

            "tool_denied" -> {
                _state.value = _state.value.copy(
                    chat = _state.value.chat + ChatItem.Error("${msg.name} — ${msg.reason}")
                )
            }

            "subagent" -> {
                _state.value = _state.value.copy(
                    chat = _state.value.chat +
                        ChatItem.Tool("subagent", msg.description, msg.final)
                )
            }

            "permission" -> {
                _permissions.value = _permissions.value +
                    PermissionRequest(msg.id, msg.name, msg.summary)
            }

            "question" -> {
                val q = msg.question
                _questions.value = _questions.value + QuestionRequest(
                    id = msg.id,
                    text = q?.get("question")?.toString()?.trim('"') ?: "",
                    options = q?.get("options")?.let { opts ->
                        (opts as? kotlinx.serialization.json.JsonArray)?.map { o ->
                            val obj = o as? kotlinx.serialization.json.JsonObject
                            obj?.get("label")?.toString()?.trim('"')
                                ?: obj?.get("description")?.toString()?.trim('"')
                                ?: o.toString()
                        } ?: emptyList()
                    } ?: emptyList(),
                )
            }

            "plan" -> {
                _plans.value = _plans.value + PlanRequest(msg.id, msg.plan)
                _state.value = _state.value.copy(
                    chat = _state.value.chat + ChatItem.Plan(msg.plan)
                )
            }

            "error" -> {
                _state.value = _state.value.copy(
                    error = msg.message,
                    busy = false,
                    chat = _state.value.chat + ChatItem.Error(msg.message),
                )
            }

            "done" -> {
                _state.value = _state.value.copy(busy = false, sessions = msg.meta?.let { meta ->
                    s.sessions.map { if (it.id == meta.id) meta else it }
                } ?: s.sessions)
                msg.usage?.let { usage ->
                    val promptTokens = usage["prompt_tokens"]?.toString()?.toDoubleOrNull() ?: 0.0
                    val completionTokens = usage["completion_tokens"]?.toString()?.toDoubleOrNull() ?: 0.0
                    val used = (promptTokens + completionTokens).toInt()
                    _lastUsage.value = used
                    _state.value = _state.value.copy(
                        contextPercent = ((used / 128000.0) * 100).toInt().coerceIn(0, 100)
                    )
                }
            }

            "interrupted" -> {
                _state.value = _state.value.copy(busy = false)
            }
        }
    }

    /** Append streamed text to the last assistant/thinking bubble. */
    private fun appendText(item: ChatItem) {
        val chat = _state.value.chat.toMutableList()
        val last = chat.lastOrNull()
        when {
            item is ChatItem.Assistant && last is ChatItem.Assistant -> {
                chat[chat.lastIndex] = last.copy(text = last.text + item.text)
            }
            item is ChatItem.Thinking && last is ChatItem.Thinking -> {
                chat[chat.lastIndex] = last.copy(text = last.text + item.text)
            }
            else -> chat.add(item)
        }
        _state.value = _state.value.copy(chat = chat)
    }
}
