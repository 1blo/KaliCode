package com.kalicode.app.net

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.encodeToString
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

/**
 * The WebSocket link to a Kali Code server.
 *
 * Reconnects automatically with a backoff, because a free-tier host spins
 * down after a period of inactivity and a phone loses its connection often.
 */
class KaliClient(
    private val scope: CoroutineScope,
) {
    private val http = OkHttpClient.Builder()
        .pingInterval(25, TimeUnit.SECONDS)
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)   // the socket is long-lived
        .build()

    private var socket: WebSocket? = null
    private var reconnectJob: Job? = null
    private var shouldReconnect = true
    private var attempts = 0

    var baseUrl: String = ""
        private set
    var token: String = ""
        private set
    var sessionId: String? = null

    private val _events = MutableSharedFlow<ServerMessage>(extraBufferCapacity = 256)
    val events: SharedFlow<ServerMessage> = _events

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected

    private val _status = MutableStateFlow(Status.Disconnected)
    val status: StateFlow<Status> = _status

    enum class Status { Disconnected, Connecting, Connected, Unauthorized, Error }

    // ------------------------------------------------------------- connect
    fun connect(serverUrl: String, accessToken: String, resumeSession: String? = null) {
        val normalized = normalizeUrl(serverUrl)
        if (normalized.isEmpty()) {
            _status.value = Status.Error
            return
        }
        baseUrl = normalized
        token = accessToken
        sessionId = resumeSession
        shouldReconnect = true
        openSocket()
    }

    fun disconnect() {
        shouldReconnect = false
        reconnectJob?.cancel()
        reconnectJob = null
        socket?.close(1000, "client closed")
        socket = null
        _connected.value = false
        _status.value = Status.Disconnected
    }

    /** Reconnect now (used by the pull-to-refresh action). */
    fun reconnectNow() {
        attempts = 0
        shouldReconnect = true
        socket?.cancel()
        socket = null
        openSocket()
    }

    private fun normalizeUrl(raw: String): String {
        var u = raw.trim().trimEnd('/')
        if (u.isEmpty()) return ""
        if (!u.startsWith("http://") && !u.startsWith("https://")) {
            u = "https://$u"
        }
        return u
    }

    private fun wsUrl(): String {
        val scheme = if (baseUrl.startsWith("https://")) "wss://" else "ws://"
        return scheme + baseUrl.removePrefix("https://").removePrefix("http://") + "/ws"
    }

    private fun openSocket() {
        _status.value = Status.Connecting
        val request = Request.Builder().url(wsUrl()).build()
        socket = http.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                attempts = 0
                _connected.value = true
                _status.value = Status.Connected
                send(ClientMessage(
                    type = "hello",
                    token = token,
                    session = sessionId,
                ))
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val msg = try {
                    Protocol.json.decodeFromString<ServerMessage>(text)
                } catch (e: Exception) {
                    null
                } ?: return
                if (msg.type == "error" && msg.message.contains("unauthorized", true)) {
                    _status.value = Status.Unauthorized
                    shouldReconnect = false
                }
                if (msg.type == "ready" && msg.session.isNotEmpty()) {
                    sessionId = msg.session
                }
                scope.launch { _events.emit(msg) }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                _connected.value = false
                _status.value = Status.Error
                scheduleReconnect()
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                _connected.value = false
                webSocket.close(1000, null)
                if (shouldReconnect) scheduleReconnect()
                else _status.value = Status.Disconnected
            }
        })
    }

    private fun scheduleReconnect() {
        if (!shouldReconnect) return
        if (reconnectJob?.isActive == true) return
        reconnectJob = scope.launch(Dispatchers.IO) {
            attempts += 1
            // 1s, 2s, 4s ... capped at 30s.
            val waitMs = (1000L shl (attempts - 1).coerceAtMost(5)).coerceAtMost(30_000L)
            delay(waitMs)
            if (shouldReconnect) openSocket()
        }
    }

    // ---------------------------------------------------------------- send
    fun send(msg: ClientMessage) {
        val s = socket ?: return
        val text = Protocol.json.encodeToString(msg)
        s.send(text)
    }

    fun prompt(text: String) = send(ClientMessage(type = "prompt", text = text))
    fun interrupt() = send(ClientMessage(type = "interrupt"))
    fun reply(id: String, answer: String) =
        send(ClientMessage(type = "reply", id = id, answer = answer))
    fun answer(id: String, value: String) =
        send(ClientMessage(type = "answer", id = id, value = value))
    fun newSession(cwd: String? = null, model: String? = null,
                   permissionMode: String? = null, worktree: Boolean = false) =
        send(ClientMessage(type = "new_session", cwd = cwd, model = model,
                          permissionMode = permissionMode, worktree = worktree))
    fun switchSession(id: String) = send(ClientMessage(type = "switch_session", session = id))
    fun setModel(model: String) = send(ClientMessage(type = "set_model", model = model))
    fun setMode(mode: String) = send(ClientMessage(type = "set_mode", mode = mode))
    fun rename(title: String) = send(ClientMessage(type = "rename", title = title))
    fun requestSessions() = send(ClientMessage(type = "sessions"))
    fun ping() = send(ClientMessage(type = "ping"))
}
