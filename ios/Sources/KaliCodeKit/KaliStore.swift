// KaliStore.swift - the whole UI state in one place.
//
// This mirrors the Android `KaliViewModel`: the store owns the client,
// folds the server's messages into a single observable state, and exposes
// the actions the UI calls.

import Foundation
import Combine

/// One entry in the conversation.
public enum ChatItem: Identifiable, Hashable, Sendable {
    case user(String, id: UUID = UUID())
    case assistant(String, id: UUID = UUID())
    case thinking(String, id: UUID = UUID())
    case error(String, id: UUID = UUID())
    case tool(name: String, summary: String, output: String, id: UUID = UUID())
    case plan(String, id: UUID = UUID())
    case toolCall(name: String, summary: String, done: Bool, ok: Bool,
                  elapsed: Double, output: String, id: UUID = UUID())

    /// A stable identity for SwiftUI's `ForEach`.
    ///
    /// It has to be unique even when the same text appears twice - two
    /// identical "OK" messages are two different rows. The `id` travels
    /// with the payload so a streamed chunk can be replaced without the
    /// row changing identity.
    public var id: UUID {
        switch self {
        case .user(_, let id): return id
        case .assistant(_, let id): return id
        case .thinking(_, let id): return id
        case .error(_, let id): return id
        case .tool(_, _, _, let id): return id
        case .plan(_, let id): return id
        case .toolCall(_, _, _, _, _, _, let id): return id
        }
    }

    /// The text of the item, for accessibility and previews.
    public var text: String {
        switch self {
        case .user(let t, _), .assistant(let t, _), .thinking(let t, _),
             .error(let t, _), .plan(let t, _):
            return t
        case .tool(let n, let s, let o, _):
            return [n, s, o].filter { !$0.isEmpty }.joined(separator: "\n")
        case .toolCall(let n, let s, _, _, _, let o, _):
            return [n, s, o].filter { !$0.isEmpty }.joined(separator: "\n")
        }
    }
}

/// A permission prompt awaiting an answer.
public struct PermissionRequest: Identifiable, Hashable, Sendable {
    public let id: String
    public let tool: String
    public let summary: String
    public init(id: String, tool: String, summary: String) {
        self.id = id
        self.tool = tool
        self.summary = summary
    }
}

/// An `AskUserQuestion` prompt awaiting an answer.
public struct QuestionRequest: Identifiable, Hashable, Sendable {
    public let id: String
    public let text: String
    public let options: [QuestionOption]
    public init(id: String, text: String, options: [QuestionOption]) {
        self.id = id
        self.text = text
        self.options = options
    }
}

/// A plan awaiting approval.
public struct PlanRequest: Identifiable, Hashable, Sendable {
    public let id: String
    public let plan: String
    public init(id: String, plan: String) {
        self.id = id
        self.plan = plan
    }
}

/// The whole state of the app.
public struct KaliState: Equatable, Sendable {
    public var serverUrl: String = ""
    public var token: String = ""
    public var connected: Bool = false
    public var sessions: [SessionInfo] = []
    public var currentSession: String? = nil
    public var chat: [ChatItem] = []
    public var busy: Bool = false
    public var model: String = Protocol.models.first ?? ""
    public var permissionMode: String = "default"
    public var cwd: String = ""
    public var contextPercent: Int = 0
    public var error: String? = nil

    public init() {}
}

/// The app's store: owns the client and publishes the state.
@MainActor
public final class KaliStore: ObservableObject {
    @Published public private(set) var state = KaliState()
    @Published public private(set) var permissions: [PermissionRequest] = []
    @Published public private(set) var questions: [QuestionRequest] = []
    @Published public private(set) var plans: [PlanRequest] = []
    @Published public private(set) var status: ConnectionStatus = .disconnected

    private let client = KaliClient()
    private var cancellables = Set<AnyCancellable>()

    /// Called whenever the server picks a session, so the app can
    /// remember it and resume the same conversation next time.
    public var onSessionChanged: ((String) -> Void)? = nil

    public init() {
        client.onMessage = { [weak self] message in
            self?.handle(message)
        }
        // Mirror the client's status into the store.
        client.$status
            .receive(on: RunLoop.main)
            .sink { [weak self] status in
                self?.status = status
                self?.state.connected = status.isOnline
            }
            .store(in: &cancellables)
    }

    // MARK: - Connect

    public func connect(serverUrl: String, token: String,
                        resumeSession: String? = nil) {
        state.serverUrl = serverUrl
        state.token = token
        state.error = nil
        client.connect(serverUrl: serverUrl, accessToken: token,
                       resumeSession: resumeSession)
    }

    public func disconnect() {
        client.disconnect()
        state.connected = false
    }

    public func reconnect() {
        client.reconnectNow()
    }

    public func clearError() {
        state.error = nil
    }

    /// Show a message to the user.
    public func report(_ message: String) {
        state.error = message
    }

    // MARK: - Actions

    public func sendPrompt(_ text: String) {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !state.busy else { return }
        state.chat.append(.user(clean))
        state.busy = true
        client.prompt(clean)
    }

    public func interrupt() {
        client.interrupt()
        state.busy = false
    }

    public func answerPermission(id: String, answer: String) {
        client.reply(id: id, answer: answer)
        permissions.removeAll { $0.id == id }
    }

    public func answerQuestion(id: String, value: String) {
        client.answer(id: id, value: value)
        questions.removeAll { $0.id == id }
    }

    public func answerPlan(id: String, answer: String) {
        client.reply(id: id, answer: answer)
        plans.removeAll { $0.id == id }
    }

    public func newSession() { client.newSession() }

    /// Ask the server for the current session list.
    public func refreshSessions() { client.requestSessions() }

    public func switchSession(id: String) {
        state.currentSession = id
        state.chat = []
        state.busy = false
        client.switchSession(id: id)
    }

    public func setModel(_ model: String) {
        state.model = model
        client.setModel(model)
    }

    public func setMode(_ mode: String) {
        state.permissionMode = mode
        client.setMode(mode)
    }

    public func rename(_ title: String) { client.rename(title) }
    public func clearChat() { state.chat = [] }

    // MARK: - Events

    private func handle(_ msg: ServerMessage) {
        switch msg.type {
        case "ready":
            state.connected = true
            if !msg.session.isEmpty {
                state.currentSession = msg.session
                onSessionChanged?(msg.session)
            }
            if !msg.sessions.isEmpty { state.sessions = msg.sessions }
            if !msg.cwd.isEmpty { state.cwd = msg.cwd }
            if !msg.model.isEmpty { state.model = msg.model }
            state.busy = false
            state.error = nil

        case "sessions":
            state.sessions = msg.sessions

        case "session_meta":
            if let meta = msg.meta {
                state.sessions = state.sessions.map { $0.id == meta.id ? meta : $0 }
                state.model = meta.model
                state.permissionMode = meta.permissionMode
                state.cwd = meta.cwd
            }

        case "thinking":
            if !msg.text.trimmingCharacters(in: .whitespaces).isEmpty {
                appendText(.thinking(msg.text))
            }

        case "text":
            appendText(.assistant(msg.text))

        case "tool_start":
            state.chat.append(.toolCall(name: msg.name, summary: msg.summary,
                                        done: false, ok: true, elapsed: 0,
                                        output: ""))

        case "tool_result":
            state.chat = state.chat.map { item in
                if case .toolCall(let name, _, let done, _, _, _, let id) = item,
                   name == msg.name, !done {
                    return .toolCall(name: name, summary: summaryOf(item),
                                     done: true, ok: msg.ok,
                                     elapsed: msg.elapsed, output: msg.output,
                                     id: id)
                }
                return item
            }

        case "tool_denied":
            state.chat.append(.error("\(msg.name) — \(msg.reason)"))

        case "subagent":
            state.chat.append(.tool(name: "subagent", summary: msg.description,
                                    output: msg.final))

        case "permission":
            permissions.append(PermissionRequest(id: msg.id, tool: msg.name,
                                                  summary: msg.summary))

        case "question":
            let q = msg.question
            questions.append(QuestionRequest(
                id: msg.id,
                text: q?.question ?? "",
                options: q?.options ?? []))

        case "plan":
            plans.append(PlanRequest(id: msg.id, plan: msg.plan))
            state.chat.append(.plan(msg.plan))

        case "error":
            state.error = msg.message
            state.busy = false
            state.chat.append(.error(msg.message))

        case "done":
            state.busy = false
            if let meta = msg.meta {
                state.sessions = state.sessions.map { $0.id == meta.id ? meta : $0 }
            }
            if let usage = msg.usage {
                let prompt = usage["prompt_tokens"]?.doubleValue ?? 0
                let completion = usage["completion_tokens"]?.doubleValue ?? 0
                let used = prompt + completion
                state.contextPercent = Int((used / 128_000.0) * 100)
                    .clamped(to: 0...100)
            }

        case "interrupted":
            state.busy = false

        default:
            break
        }
    }

    /// The summary of a tool call, whatever state it is in.
    private func summaryOf(_ item: ChatItem) -> String {
        if case .toolCall(_, let summary, _, _, _, _, _) = item { return summary }
        return ""
    }

    /// Append streamed text to the last assistant/thinking bubble.
    ///
    /// The row keeps its original `id` so SwiftUI does not rebuild it
    /// (and lose the scroll position) on every token.
    private func appendText(_ item: ChatItem) {
        guard let last = state.chat.last else {
            state.chat.append(item)
            return
        }
        switch (item, last) {
        case (.assistant(let text, _), .assistant(let previous, let id)):
            state.chat[state.chat.count - 1] = .assistant(previous + text, id: id)
        case (.thinking(let text, _), .thinking(let previous, let id)):
            state.chat[state.chat.count - 1] = .thinking(previous + text, id: id)
        default:
            state.chat.append(item)
        }
    }
}

extension Int {
    /// Clamp a number into a range.
    func clamped(to range: ClosedRange<Int>) -> Int {
        min(max(self, range.lowerBound), range.upperBound)
    }
}
