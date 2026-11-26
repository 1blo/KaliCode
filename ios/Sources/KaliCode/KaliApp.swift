// KaliApp.swift - the SwiftUI application.
//
// The layout mirrors the Android app: a title bar with the session name
// and a new-session button, the conversation, and a composer with the
// model, the permission mode and the context usage.

import SwiftUI
import KaliCodeKit

@main
struct KaliCodeApp: App {
    @StateObject private var store = KaliStore()
    @AppStorage("kali_session") private var savedSession = ""

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .preferredColorScheme(.dark)
                .tint(Theme.accent)
                .onAppear {
                    // Remember the session so the app resumes the same
                    // conversation next time it opens.
                    store.onSessionChanged = { id in
                        savedSession = id
                    }
                }
        }
    }
}

/// The connect screen and the chat, chosen by the connection state.
struct RootView: View {
    @EnvironmentObject private var store: KaliStore

    var body: some View {
        if store.state.connected {
            ChatView()
        } else {
            ConnectView()
        }
    }
}

// MARK: - Connect

struct ConnectView: View {
    @EnvironmentObject private var store: KaliStore
    @AppStorage("kali_server_url") private var savedUrl = ""
    @AppStorage("kali_token") private var savedToken = ""
    @AppStorage("kali_session") private var savedSession = ""

    @State private var url = ""
    @State private var token = ""
    @FocusState private var focused: Field?

    private enum Field { case url, token }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("Kali Code")
                        .font(.system(size: 30, weight: .bold))
                        .foregroundStyle(Theme.fg)

                    Text("An accurate copy of the Claude Code agentic coding CLI")
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.dim)
                        .padding(.top, 4)
                        .padding(.bottom, 28)

                    field("Server URL",
                           placeholder: "https://kali-code.onrender.com",
                           text: $url,
                           field: .url)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .submitLabel(.next)
                        .onSubmit { focused = .token }

                    field("Access token",
                           placeholder: "the token printed by the server",
                           text: $token,
                           field: .token)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textContentType(.password)
                        .submitLabel(.go)
                        .onSubmit { connect() }
                        .padding(.top, 14)

                    if let error = store.state.error {
                        Text(error)
                            .font(.system(size: 12))
                            .foregroundStyle(Theme.red)
                            .padding(.top, 10)
                    }

                    Button(action: connect) {
                        HStack(spacing: 8) {
                            if store.status == .connecting {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .tint(Color(hex: 0x17140F))
                            }
                            Text(store.status == .connecting ? "Connecting…" : "Connect")
                                .font(.system(size: 16, weight: .semibold))
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .background(Theme.accent)
                        .foregroundStyle(Color(hex: 0x17140F))
                        .clipShape(RoundedRectangle(cornerRadius: Theme.corner))
                    }
                    .padding(.top, 22)

                    Text("The token is printed by the server when it starts. "
                         + "The desktop app writes it to "
                         + "~/Library/Application Support/KaliCode/desktop.json.")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.dimmer)
                        .padding(.top, 16)
                }
                .padding(24)
                .frame(maxWidth: 480)
                .frame(maxWidth: .infinity)
            }
        }
        .onAppear {
            url = savedUrl
            token = savedToken
            // Reconnect to the last server without asking.
            if !savedUrl.isEmpty && !savedToken.isEmpty {
                store.connect(serverUrl: savedUrl, token: savedToken,
                              resumeSession: savedSession.isEmpty ? nil : savedSession)
            }
        }
    }

    private func field(_ label: String, placeholder: String, text: Binding<String>,
                       field: Field) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Theme.dim)
            TextField(placeholder, text: text)
                .textFieldStyle(.plain)
                .padding(.horizontal, 14)
                .padding(.vertical, 13)
                .background(Theme.panel)
                .foregroundStyle(Theme.fg)
                .clipShape(RoundedRectangle(cornerRadius: Theme.corner))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.corner)
                        .stroke(focused == field ? Theme.accent : Theme.border,
                                lineWidth: 1)
                )
                .focused($focused, equals: field)
        }
    }

    private func connect() {
        let cleanUrl = url.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanToken.isEmpty else {
            store.report("Enter the access token the server printed.")
            return
        }
        guard !cleanUrl.isEmpty else {
            store.report("Enter the server URL.")
            return
        }
        savedUrl = cleanUrl
        savedToken = cleanToken
        store.connect(serverUrl: cleanUrl, token: cleanToken,
                      resumeSession: savedSession.isEmpty ? nil : savedSession)
    }
}
// MARK: - Chat

struct ChatView: View {
    @EnvironmentObject private var store: KaliStore
    @State private var showSessions = false
    @State private var text = ""
    @State private var showModelPicker = false
    @State private var showModePicker = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ConversationView()
                PromptBar(text: $text,
                          showModelPicker: $showModelPicker,
                          showModePicker: $showModePicker)
            }
            .background(Theme.bg)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        showSessions = true
                    } label: {
                        Image(systemName: "list.bullet")
                            .foregroundStyle(Theme.dim)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        store.newSession()
                    } label: {
                        Image(systemName: "plus")
                            .foregroundStyle(Theme.dim)
                    }
                }
            }
            .sheet(isPresented: $showSessions) {
                SessionSheet()
            }
            .confirmationDialog("Model", isPresented: $showModelPicker,
                                titleVisibility: .visible) {
                ForEach(Protocol.models, id: \.self) { model in
                    Button {
                        store.setModel(model)
                    } label: {
                        if model == store.state.model {
                            Label(Protocol.prettyModel(model), systemImage: "checkmark")
                        } else {
                            Text(Protocol.prettyModel(model))
                        }
                    }
                }
            }
            .confirmationDialog("Permission mode", isPresented: $showModePicker,
                                titleVisibility: .visible) {
                ForEach(Protocol.modes) { mode in
                    Button {
                        store.setMode(mode.id)
                    } label: {
                        if mode.id == store.state.permissionMode {
                            Label(mode.label, systemImage: "checkmark")
                        } else {
                            Text(mode.label)
                        }
                    }
                }
            }
        }
    }

    private var title: String {
        if store.state.busy { return "Working…" }
        let current = store.state.sessions.first {
            $0.id == store.state.currentSession
        }
        return current?.displayTitle ?? "Kali Code"
    }
}

// MARK: - The conversation

struct ConversationView: View {
    @EnvironmentObject private var store: KaliStore

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if store.state.chat.isEmpty && store.permissions.isEmpty {
                        emptyState
                    }

                    ForEach(store.state.chat) { item in
                        ChatRow(item: item)
                            .id(item.id)
                    }

                    ForEach(store.permissions) { request in
                        PermissionCard(request: request) { answer in
                            store.answerPermission(id: request.id, answer: answer)
                        }
                        .id("perm-" + request.id)
                    }

                    ForEach(store.questions) { request in
                        QuestionCard(request: request) { value in
                            store.answerQuestion(id: request.id, value: value)
                        }
                        .id("q-" + request.id)
                    }

                    ForEach(store.plans) { request in
                        PlanApprovalCard(request: request) { answer in
                            store.answerPlan(id: request.id, answer: answer)
                        }
                        .id("plan-" + request.id)
                    }

                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: store.state.chat.count) { _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
            .onChange(of: store.permissions.count) { _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }
    private var emptyState: some View {
        VStack(spacing: 8) {
            Text("Ask Kali Code…")
                .font(.system(size: 15))
                .foregroundStyle(Theme.dimmer)
            Text("The agent runs on your server, not on this phone.")
                .font(.system(size: 11))
                .foregroundStyle(Theme.dimmer)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 60)
    }
}

// MARK: - Chat rows

struct ChatRow: View {
    let item: ChatItem

    var body: some View {
        switch item {
        case .user(let text, _):
            HStack {
                Spacer(minLength: 40)
                Text(text)
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.fg)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 9)
                    .background(Theme.panel2)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
                            .stroke(Theme.border, lineWidth: 1)
                    )
                    .textSelection(.enabled)
            }

        case .assistant(let text, _):
            VStack(alignment: .leading, spacing: 3) {
                Text("KALI")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Theme.accent)
                Text(text)
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.fg)
                    .textSelection(.enabled)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

        case .thinking(let text, _):
            VStack(alignment: .leading, spacing: 3) {
                Text("thinking")
                    .font(.system(size: 10, weight: .medium))
                    .italic()
                    .foregroundStyle(Theme.dimmer)
                Text(text)
                    .font(.system(size: 12))
                    .italic()
                    .foregroundStyle(Theme.dim)
                    .textSelection(.enabled)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

        case .error(let text, _):
            HStack(alignment: .top, spacing: 10) {
                Rectangle()
                    .fill(Theme.red)
                    .frame(width: 2)
                Text(text)
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.red)
                    .textSelection(.enabled)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

        case .plan(let text, _):
            VStack(alignment: .leading, spacing: 5) {
                Text("Plan")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Theme.blue)
                Text(text)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.dim)
            }
            .padding(11)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Theme.blue, lineWidth: 1)
            )

        case .tool(let name, let summary, let output, _):
            ToolCard(name: name, summary: summary, output: output,
                     done: true, ok: true, elapsed: 0)

        case .toolCall(let name, let summary, let done, let ok, let elapsed,
                       let output, _):
            ToolCard(name: name, summary: summary, output: output,
                     done: done, ok: ok, elapsed: elapsed)
        }
    }
}

/// A tool call, collapsed by default.
struct ToolCard: View {
    let name: String
    let summary: String
    let output: String
    let done: Bool
    let ok: Bool
    let elapsed: Double

    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text(name)
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.purple)
                Text(statusText)
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.dimmer)
            }

            if !summary.isEmpty {
                Text(summary)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.dim)
                    .lineLimit(3)
            }

            if !output.isEmpty {
                Text(expanded ? output : String(output.prefix(400)))
                    .font(.system(size: 10.5, design: .monospaced))
                    .foregroundStyle(Theme.dim)
                    .padding(7)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.bg)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .onTapGesture { expanded.toggle() }

                if output.count > 400 {
                    Text(expanded ? "tap to collapse" : "tap to expand")
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.dimmer)
                        .onTapGesture { expanded.toggle() }
                }
            }
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Theme.border, lineWidth: 1)
        )
    }

    private var statusText: String {
        if !done { return "running…" }
        var text = ok ? "done" : "failed"
        if elapsed > 0 { text += " in \(String(format: "%.1f", elapsed))s" }
        return text
    }
}

// MARK: - Prompt cards

struct PermissionCard: View {
    let request: PermissionRequest
    let onAnswer: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Permission needed — \(request.tool)")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.fg)

            if !request.summary.isEmpty {
                Text(request.summary)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.dim)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.bg)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            }

            HStack(spacing: 7) {
                button("Allow", color: Theme.accent) { onAnswer("allow") }
                button("Always", color: Theme.yellow) { onAnswer("always") }
                button("Deny", color: Theme.red) { onAnswer("deny") }
            }
        }
        .padding(13)
        .background(Theme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 11))
        .overlay(
            RoundedRectangle(cornerRadius: 11)
                .stroke(Theme.yellow, lineWidth: 1)
        )
    }

    private func button(_ label: String, color: Color,
                        action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(label == "Allow" ? Color(hex: 0x17140F) : color)
                .frame(maxWidth: .infinity)
                .frame(height: 36)
                .background(label == "Allow" ? color : color.opacity(0.16))
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }
}

struct QuestionCard: View {
    let request: QuestionRequest
    let onAnswer: (String) -> Void

    @State private var custom = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Question")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.purple)

            Text(request.text)
                .font(.system(size: 13))
                .foregroundStyle(Theme.fg)

            ForEach(request.options) { option in
                Button {
                    onAnswer(option.label)
                } label: {
                    HStack {
                        Text(option.label)
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.accent)
                        Spacer()
                        if !option.description.isEmpty {
                            Text(option.description)
                                .font(.system(size: 11))
                                .foregroundStyle(Theme.dimmer)
                                .lineLimit(1)
                        }
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.panel2)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
            }

            HStack(spacing: 8) {
                TextField("or type your own answer", text: $custom)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .padding(.horizontal, 11)
                    .padding(.vertical, 9)
                    .background(Theme.bg)
                    .foregroundStyle(Theme.fg)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Theme.border, lineWidth: 1)
                    )
                    .submitLabel(.send)
                    .onSubmit { submit() }

                Button(action: submit) {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(Color(hex: 0x17140F))
                        .frame(width: 36, height: 36)
                        .background(Theme.accent)
                        .clipShape(Circle())
                }
            }
        }
        .padding(13)
        .background(Theme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 11))
        .overlay(
            RoundedRectangle(cornerRadius: 11)
                .stroke(Theme.purple, lineWidth: 1)
        )
    }

    private func submit() {
        let clean = custom.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        onAnswer(clean)
    }
}

struct PlanApprovalCard: View {
    let request: PlanRequest
    let onAnswer: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Plan ready for approval")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.blue)

            ScrollView {
                Text(request.plan)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.dim)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 200)

            HStack(spacing: 7) {
                Button {
                    onAnswer("approve")
                } label: {
                    Text("Approve")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(hex: 0x17140F))
                        .frame(maxWidth: .infinity)
                        .frame(height: 36)
                        .background(Theme.accent)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                Button {
                    onAnswer("reject")
                } label: {
                    Text("Reject")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Theme.red)
                        .frame(maxWidth: .infinity)
                        .frame(height: 36)
                        .background(Theme.red.opacity(0.16))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
            }
        }
        .padding(13)
        .background(Theme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 11))
        .overlay(
            RoundedRectangle(cornerRadius: 11)
                .stroke(Theme.blue, lineWidth: 1)
        )
    }
}

// MARK: - The composer

struct PromptBar: View {
    @EnvironmentObject private var store: KaliStore
    @Binding var text: String
    @Binding var showModelPicker: Bool
    @Binding var showModePicker: Bool

    @FocusState private var focused: Bool

    var body: some View {
        VStack(spacing: 6) {
            TextField("Ask Kali Code…", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 15))
                .lineLimit(1...6)
                .padding(.horizontal, 14)
                .padding(.vertical, 11)
                .background(Theme.panel)
                .foregroundStyle(Theme.fg)
                .clipShape(RoundedRectangle(cornerRadius: 20))
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(focused ? Theme.accent : Theme.border, lineWidth: 1)
                )
                .focused($focused)
                .padding(.horizontal, 12)
                .padding(.top, 8)

            HStack(spacing: 12) {
                Button {
                    showModelPicker = true
                } label: {
                    Text(Protocol.prettyModel(store.state.model))
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.dim)
                        .lineLimit(1)
                }

                Button {
                    showModePicker = true
                } label: {
                    Text(Protocol.modeLabel(store.state.permissionMode))
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.dim)
                }

                Text("\(store.state.contextPercent)%")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.dimmer)

                Spacer()

                if store.state.busy {
                    Button {
                        store.interrupt()
                    } label: {
                        Image(systemName: "stop.fill")
                            .font(.system(size: 13))
                            .foregroundStyle(.white)
                            .frame(width: 36, height: 36)
                            .background(Theme.red)
                            .clipShape(Circle())
                    }
                } else {
                    Button {
                        store.sendPrompt(text)
                        text = ""
                    } label: {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(Color(hex: 0x17140F))
                            .frame(width: 36, height: 36)
                            .background(Theme.accent)
                            .clipShape(Circle())
                    }
                    .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty)
                    .opacity(text.trimmingCharacters(in: .whitespaces).isEmpty ? 0.4 : 1)
                }
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 8)
        }
        .background(Theme.bg)
        .overlay(alignment: .top) {
            Rectangle().fill(Theme.border).frame(height: 1)
        }
    }
}

// MARK: - Sessions

struct SessionSheet: View {
    @EnvironmentObject private var store: KaliStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                ForEach(store.state.sessions) { session in
                    Button {
                        store.switchSession(id: session.id)
                        dismiss()
                    } label: {
                        HStack(spacing: 10) {
                            Circle()
                                .fill(color(for: session))
                                .frame(width: 7, height: 7)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(session.displayTitle)
                                    .font(.system(size: 13))
                                    .foregroundStyle(
                                        session.id == store.state.currentSession
                                            ? Theme.accent : Theme.fg)
                                    .lineLimit(1)
                                Text(session.cwd)
                                    .font(.system(size: 10))
                                    .foregroundStyle(Theme.dimmer)
                                    .lineLimit(1)
                            }
                            Spacer()
                            if session.worktree {
                                Image(systemName: "arrow.triangle.branch")
                                    .font(.system(size: 11))
                                    .foregroundStyle(Theme.dim)
                            }
                        }
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.bg)
            .navigationTitle("Sessions")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                // The list may be stale after another client changed it.
                store.refreshSessions()
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Disconnect") {
                        store.disconnect()
                        dismiss()
                    }
                    .foregroundStyle(Theme.dim)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("New") {
                        store.newSession()
                        dismiss()
                    }
                    .foregroundStyle(Theme.accent)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func color(for session: SessionInfo) -> Color {
        if session.isRunning { return Theme.green }
        if session.isAwaiting { return Theme.yellow }
        return Theme.dimmer
    }
}
