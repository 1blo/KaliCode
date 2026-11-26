// KaliClient.swift - the WebSocket link to a Kali Code server.
//
// The phone is always a client. It reconnects automatically with a
// backoff, because a free-tier host spins down after a period of
// inactivity and a phone loses its connection often.

import Foundation
import Combine

/// The state of the connection to the server.
public enum ConnectionStatus: Equatable, Sendable {
    case disconnected
    case connecting
    case connected
    case unauthorized
    case error(String)

    public var isOnline: Bool { self == .connected }
}

/// The transport to a Kali Code server.
@MainActor
public final class KaliClient: ObservableObject {
    // MARK: Published state

    @Published public private(set) var status: ConnectionStatus = .disconnected
    @Published public private(set) var sessionId: String? = nil
    /// A callback for every message the server sends.
    public var onMessage: ((ServerMessage) -> Void)? = nil

    // MARK: Private state

    private var task: URLSessionWebSocketTask? = nil
    private var session: URLSession? = nil
    private var reconnectWork: Task<Void, Never>? = nil
    private var shouldReconnect = true
    private var attempts = 0

    private(set) public var baseUrl: String = ""
    private(set) public var token: String = ""

    public init() {}

    // MARK: - Connect

    /// Connect to a server and start listening.
    public func connect(serverUrl: String, accessToken: String,
                        resumeSession: String? = nil) {
        let normalized = Self.normalizeUrl(serverUrl)
        guard !normalized.isEmpty else {
            status = .error("Enter the server URL.")
            return
        }
        baseUrl = normalized
        token = accessToken
        sessionId = resumeSession
        shouldReconnect = true
        openSocket()
    }

    /// Close the connection and stop reconnecting.
    public func disconnect() {
        shouldReconnect = false
        reconnectWork?.cancel()
        reconnectWork = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        status = .disconnected
    }

    /// Reconnect right now (the pull-to-refresh action).
    public func reconnectNow() {
        attempts = 0
        shouldReconnect = true
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        openSocket()
    }

    // MARK: - URLs

    /// Turn what the user typed into a usable base URL.
    static func normalizeUrl(_ raw: String) -> String {
        var u = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while u.hasSuffix("/") { u.removeLast() }
        if u.isEmpty { return "" }
        if !u.hasPrefix("http://") && !u.hasPrefix("https://") {
            u = "https://" + u
        }
        return u
    }

    /// The WebSocket URL for the server.
    func webSocketUrl() -> URL? {
        let scheme = baseUrl.hasPrefix("https://") ? "wss://" : "ws://"
        var host = baseUrl
        if host.hasPrefix("https://") { host.removeFirst(8) }
        if host.hasPrefix("http://") { host.removeFirst(7) }
        return URL(string: scheme + host + "/ws")
    }

    // MARK: - Socket

    private func openSocket() {
        guard let url = webSocketUrl() else {
            status = .error("That server URL is not valid.")
            return
        }
        status = .connecting

        if session == nil {
            let config = URLSessionConfiguration.default
            config.waitsForConnectivity = true
            config.timeoutIntervalForRequest = 30
            session = URLSession(configuration: config)
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        let socket = session!.webSocketTask(with: request)
        task = socket
        socket.resume()
        receiveNext()

        // The server closes the connection unless the *first* message is
        // the handshake that carries the access token.
        var hello = ClientMessage(type: "hello")
        hello.token = token
        hello.session = sessionId
        send(hello)
    }

    private func receiveNext() {
        task?.receive { [weak self] result in
            // The completion handler runs on URLSession's queue, not the
            // main actor, so every hop back has to be explicit.
            Task { @MainActor [weak self] in
                guard let self else { return }
                switch result {
                case .success(let message):
                    switch message {
                    case .string(let text):
                        self.handle(text)
                    case .data(let data):
                        if let text = String(data: data, encoding: .utf8) {
                            self.handle(text)
                        }
                    @unknown default:
                        break
                    }
                    self.receiveNext()

                case .failure:
                    self.status = .error("Connection lost.")
                    self.scheduleReconnect()
                }
            }
        }
    }

    private func handle(_ text: String) {
        guard let data = text.data(using: .utf8),
              let msg = try? Protocol.decoder.decode(ServerMessage.self, from: data)
        else { return }

        if msg.type == "error",
           msg.message.lowercased().contains("unauthorized") {
            status = .unauthorized
            shouldReconnect = false
        }
        if msg.type == "ready", !msg.session.isEmpty {
            sessionId = msg.session
        }
        onMessage?(msg)
    }

    private func scheduleReconnect() {
        guard shouldReconnect, reconnectWork == nil else { return }
        reconnectWork = Task { @MainActor [weak self] in
            guard let self else { return }
            attempts += 1
            // 1s, 2s, 4s ... capped at 30s.
            let seconds = min(pow(2.0, Double(attempts - 1)), 30)
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            self.reconnectWork = nil
            if self.shouldReconnect { self.openSocket() }
        }
    }

    // MARK: - Send

    /// Send a message to the server.
    public func send(_ message: ClientMessage) {
        guard let task,
              let data = try? Protocol.encoder.encode(message),
              let text = String(data: data, encoding: .utf8)
        else { return }
        task.send(.string(text)) { _ in }
    }

    public func prompt(_ text: String) {
        var m = ClientMessage(type: "prompt")
        m.text = text
        send(m)
    }

    public func interrupt() {
        send(ClientMessage(type: "interrupt"))
    }

    public func reply(id: String, answer: String) {
        var m = ClientMessage(type: "reply")
        m.id = id
        m.answer = answer
        send(m)
    }

    public func answer(id: String, value: String) {
        var m = ClientMessage(type: "answer")
        m.id = id
        m.value = value
        send(m)
    }

    public func newSession(cwd: String? = nil, model: String? = nil,
                           permissionMode: String? = nil, worktree: Bool = false) {
        var m = ClientMessage(type: "new_session")
        m.cwd = cwd
        m.model = model
        m.permissionMode = permissionMode
        m.worktree = worktree
        send(m)
    }

    public func switchSession(id: String) {
        var m = ClientMessage(type: "switch_session")
        m.session = id
        send(m)
    }

    public func setModel(_ model: String) {
        var m = ClientMessage(type: "set_model")
        m.model = model
        send(m)
    }

    public func setMode(_ mode: String) {
        var m = ClientMessage(type: "set_mode")
        m.mode = mode
        send(m)
    }

    public func rename(_ title: String) {
        var m = ClientMessage(type: "rename")
        m.title = title
        send(m)
    }

    public func requestSessions() {
        send(ClientMessage(type: "sessions"))
    }
}
