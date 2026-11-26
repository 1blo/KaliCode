// Protocol.swift - the Kali Code wire protocol.
//
// The phone is always a *client*: it never executes the agent. It talks to
// the same `kali/serve.py` WebSocket API that the desktop GUI and the
// Android app use.
//
// The messages are decoded leniently: the server may add fields at any
// time, and an unknown field must never break the app.

import Foundation

// MARK: - Sessions

/// One session as the server describes it.
public struct SessionInfo: Codable, Identifiable, Hashable, Sendable {
    public var id: String = ""
    public var title: String = ""
    public var cwd: String = ""
    public var model: String = ""
    public var permissionMode: String = "default"
    public var worktree: Bool = false
    public var created: Double = 0
    public var updated: Double = 0
    public var archived: Bool = false
    public var parent: String? = nil
    public var status: String = "idle"
    public var usage: [String: UsageValue]? = nil
    public var messageCount: Int = 0
    public var branch: String = ""

    public init() {}

    /// The title to show, falling back to a generic label.
    public var displayTitle: String {
        title.isEmpty ? "New session" : title
    }

    /// Whether the agent is busy with this session right now.
    public var isRunning: Bool {
        status == "running"
    }

    /// Whether the agent is waiting for the user to approve something.
    public var isAwaiting: Bool {
        status == "awaiting_permission"
    }
}

/// A usage number. The server may send it as a number or as a string.
public enum UsageValue: Codable, Hashable, Sendable {
    case number(Double)
    case string(String)

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let d = try? container.decode(Double.self) {
            self = .number(d)
        } else {
            self = .string(try container.decode(String.self))
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .number(let d): try container.encode(d)
        case .string(let s): try container.encode(s)
        }
    }

    /// The value as a number, when it can be read as one.
    public var doubleValue: Double? {
        switch self {
        case .number(let d): return d
        case .string(let s): return Double(s)
        }
    }
}

// MARK: - Questions

/// The payload of an `AskUserQuestion` prompt.
public struct QuestionPayload: Codable, Hashable, Sendable {
    public var question: String = ""
    public var options: [QuestionOption] = []
    /// Anything else the server sent (header, multiSelect, ...).
    public var extra: [String: JSONValue] = [:]

    public init() {}

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DynamicKey.self)
        question = (try? container.decodeIfPresent(String.self, forKey: .init("question"))) ?? ""
        options = (try? container.decodeIfPresent([QuestionOption].self, forKey: .init("options"))) ?? []
        var rest: [String: JSONValue] = [:]
        for key in container.allKeys {
            let name = key.stringValue
            if name == "question" || name == "options" { continue }
            if let value = try? container.decode(JSONValue.self, forKey: key) {
                rest[name] = value
            }
        }
        extra = rest
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: DynamicKey.self)
        try container.encode(question, forKey: .init("question"))
        try container.encode(options, forKey: .init("options"))
    }
}

/// One selectable answer.
public struct QuestionOption: Codable, Hashable, Sendable, Identifiable {
    public var id: String { label }
    public var label: String = ""
    public var description: String = ""

    public init() {}
    public init(label: String, description: String = "") {
        self.label = label
        self.description = description
    }

    public init(from decoder: Decoder) throws {
        if let text = try? decoder.singleValueContainer().decode(String.self) {
            label = text
            return
        }
        let container = try decoder.container(keyedBy: DynamicKey.self)
        label = (try? container.decodeIfPresent(String.self, forKey: .init("label"))) ?? ""
        description = (try? container.decodeIfPresent(String.self, forKey: .init("description"))) ?? ""
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: DynamicKey.self)
        try container.encode(label, forKey: .init("label"))
        if !description.isEmpty {
            try container.encode(description, forKey: .init("description"))
        }
    }
}

// MARK: - Server messages

/// A message from the server.
public struct ServerMessage: Codable, Sendable {
    public var type: String = ""
    /// The session id. Older servers put the whole session object here
    /// instead of in `meta`, so this field tolerates both shapes.
    public var session: String = ""
    public var model: String = ""
    public var cwd: String = ""
    public var version: String = ""
    public var sessions: [SessionInfo] = []
    public var text: String = ""
    public var name: String = ""
    public var args: [String: JSONValue]? = nil
    public var ok: Bool = true
    public var output: String = ""
    public var elapsed: Double = 0
    public var reason: String = ""
    public var id: String = ""
    public var summary: String = ""
    public var question: QuestionPayload? = nil
    public var plan: String = ""
    public var path: String = ""
    public var diff: String = ""
    public var message: String = ""
    public var usage: [String: UsageValue]? = nil
    public var description: String = ""
    public var final: String = ""
    public var background: Bool = false
    public var server: String = ""
    public var count: Int = 0
    public var meta: SessionInfo? = nil
    public var tool: String = ""

    public init() {}

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DynamicKey.self)

        func str(_ key: String) -> String {
            (try? container.decodeIfPresent(String.self, forKey: .init(key))) ?? ""
        }
        func int(_ key: String) -> Int {
            (try? container.decodeIfPresent(Int.self, forKey: .init(key))) ?? 0
        }
        func dbl(_ key: String) -> Double {
            (try? container.decodeIfPresent(Double.self, forKey: .init(key))) ?? 0
        }
        func bool(_ key: String) -> Bool {
            (try? container.decodeIfPresent(Bool.self, forKey: .init(key))) ?? true
        }

        type = str("type")
        model = str("model")
        cwd = str("cwd")
        version = str("version")
        sessions = (try? container.decodeIfPresent([SessionInfo].self, forKey: .init("sessions"))) ?? []
        text = str("text")
        name = str("name")
        args = try? container.decodeIfPresent([String: JSONValue].self, forKey: .init("args"))
        ok = bool("ok")
        output = str("output")
        elapsed = dbl("elapsed")
        reason = str("reason")
        id = str("id")
        summary = str("summary")
        question = try? container.decodeIfPresent(QuestionPayload.self, forKey: .init("question"))
        plan = str("plan")
        path = str("path")
        diff = str("diff")
        message = str("message")
        usage = try? container.decodeIfPresent([String: UsageValue].self, forKey: .init("usage"))
        description = str("description")
        final = str("final")
        background = bool("background")
        server = str("server")
        count = int("count")
        tool = str("tool")

        // The session id and the session object share the name "session"
        // in different server versions. Accept either.
        //
        // A string decode that succeeds means the field holds an id; a
        // type mismatch means it holds the session object.
        let sessionKey = DynamicKey("session")
        if let asString = try? container.decodeIfPresent(String.self, forKey: sessionKey),
           let id = asString {
            session = id
            meta = try? container.decodeIfPresent(SessionInfo.self, forKey: .init("meta"))
        } else {
            session = ""
            if let asObject = try? container.decodeIfPresent(SessionInfo.self,
                                                           forKey: sessionKey),
               let object = asObject {
                meta = object
                session = object.id
            } else {
                meta = try? container.decodeIfPresent(SessionInfo.self, forKey: .init("meta"))
            }
        }
    }
}

// MARK: - Client messages

/// A message to the server.
public struct ClientMessage: Codable, Sendable {
    public var type: String
    public var token: String? = nil
    public var session: String? = nil
    public var text: String? = nil
    public var id: String? = nil
    public var answer: String? = nil
    public var value: String? = nil
    public var model: String? = nil
    public var mode: String? = nil
    public var title: String? = nil
    public var cwd: String? = nil
    public var permissionMode: String? = nil
    public var worktree: Bool? = nil

    public init(type: String) {
        self.type = type
    }
}

// MARK: - Helpers

/// A coding key that accepts any string, so unknown fields are ignored.
struct DynamicKey: CodingKey {
    var stringValue: String
    var intValue: Int? = nil

    init(_ stringValue: String) {
        self.stringValue = stringValue
    }

    init?(stringValue: String) {
        self.stringValue = stringValue
    }

    init?(intValue: Int) {
        self.stringValue = String(intValue)
        self.intValue = intValue
    }
}

/// A loose JSON value, used for the free-form parts of the protocol.
public enum JSONValue: Codable, Hashable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let v = try? container.decode(Bool.self) {
            self = .bool(v)
        } else if let v = try? container.decode(Double.self) {
            self = .number(v)
        } else if let v = try? container.decode(String.self) {
            self = .string(v)
        } else if let v = try? container.decode([String: JSONValue].self) {
            self = .object(v)
        } else if let v = try? container.decode([JSONValue].self) {
            self = .array(v)
        } else {
            self = .null
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .number(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        case .object(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .null: try container.encodeNil()
        }
    }

    /// A human-readable rendering, used when a tool's arguments have to be
    /// shown as text.
    public var displayText: String {
        switch self {
        case .string(let v): return v
        case .number(let v): return String(format: "%g", v)
        case .bool(let v): return v ? "true" : "false"
        case .null: return ""
        case .object, .array:
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            guard let data = try? encoder.encode(self),
                  let text = String(data: data, encoding: .utf8) else {
                return "\(self)"
            }
            return text
        }
    }
}

// MARK: - The protocol itself

/// A permission mode the app can select.
public struct PermissionMode: Identifiable, Hashable, Sendable {
    public let id: String
    public let label: String

    public init(id: String, label: String) {
        self.id = id
        self.label = label
    }
}

public enum Protocol {
    /// The JSON encoder used for outgoing messages.
    public static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.outputFormatting = [.sortedKeys]
        return e
    }()

    /// The JSON decoder used for incoming messages.
    public static let decoder = JSONDecoder()

    /// The models the server offers.
    public static let models = [
        "stepfun-ai/step-5-preview",
        "moonshotai/kimi-k3.1-pro",
        "minimaxai/minimax-m3.1-flash",
    ]

    /// The permission modes the app may select. Bypass is not offered on
    /// mobile - the agent runs on the server and a blanket bypass is too
    /// easy to trigger by accident.
    public static let modes: [PermissionMode] = [
        PermissionMode(id: "default", label: "Manual"),
        PermissionMode(id: "acceptEdits", label: "Accept edits"),
        PermissionMode(id: "plan", label: "Plan"),
        PermissionMode(id: "auto", label: "Auto"),
    ]

    /// A short, readable name for a model id.
    public static func prettyModel(_ id: String) -> String {
        guard let slash = id.lastIndex(of: "/") else { return id }
        return String(id[id.index(after: slash)...]).replacingOccurrences(of: "-", with: " ")
    }

    /// The label for a permission mode id.
    public static func modeLabel(_ id: String) -> String {
        modes.first { $0.id == id }?.label ?? id
    }
}
