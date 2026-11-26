package com.kalicode.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kalicode.app.KaliViewModel
import com.kalicode.app.net.KaliClient
import com.kalicode.app.net.Protocol
import com.kalicode.app.net.SessionInfo
import com.kalicode.app.ui.theme.Accent
import com.kalicode.app.ui.theme.Bg
import com.kalicode.app.ui.theme.Blue
import com.kalicode.app.ui.theme.Border
import com.kalicode.app.ui.theme.Dim
import com.kalicode.app.ui.theme.Dimmer
import com.kalicode.app.ui.theme.Fg
import com.kalicode.app.ui.theme.Green
import com.kalicode.app.ui.theme.Panel
import com.kalicode.app.ui.theme.Panel2
import com.kalicode.app.ui.theme.Panel3
import com.kalicode.app.ui.theme.Purple
import com.kalicode.app.ui.theme.Red
import com.kalicode.app.ui.theme.Yellow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun KaliApp(vm: KaliViewModel) {
    val state by vm.state.collectAsStateWithLifecycle()

    if (!state.connected) {
        ConnectScreen(vm)
        return
    }

    var showSessions by remember { mutableStateOf(false) }

    Scaffold(
        containerColor = Bg,
        topBar = {
            TopAppBar(
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Panel,
                    titleContentColor = Fg,
                    actionIconContentColor = Dim,
                ),
                navigationIcon = {
                    IconButton(onClick = { showSessions = true }) {
                        Icon(Icons.Default.ArrowBack, "Sessions", tint = Dim)
                    }
                },
                title = {
                    Column {
                        Text(
                            state.sessions.firstOrNull { it.id == state.currentSession }
                                ?.title ?: "Kali Code",
                            fontSize = 15.sp,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        if (state.busy) {
                            Text("Working…", fontSize = 11.sp, color = Green)
                        }
                    }
                },
                actions = {
                    IconButton(onClick = { vm.newSession() }) {
                        Icon(Icons.Default.Add, "New session", tint = Dim)
                    }
                },
            )
        },
        bottomBar = {
            PromptBar(vm, state)
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            if (state.showArchived) {
                Text(
                    "Archived sessions are hidden on mobile",
                    color = Dimmer,
                    fontSize = 11.sp,
                    modifier = Modifier.padding(8.dp),
                )
            }
            ChatList(vm, state)
        }
    }

    if (showSessions) {
        SessionSheet(vm, state) { showSessions = false }
    }
}

// ------------------------------------------------------------------ connect
@Composable
fun ConnectScreen(vm: KaliViewModel) {
    val state by vm.state.collectAsStateWithLifecycle()
    var url by remember { mutableStateOf(state.serverUrl) }
    var token by remember { mutableStateOf(state.token) }

    Surface(color = Bg, modifier = Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
        ) {
            Text("Kali Code", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Fg)
            Text(
                "An accurate copy of the Claude Code agentic coding CLI",
                color = Dim, fontSize = 13.sp,
                modifier = Modifier.padding(top = 4.dp, bottom = 28.dp),
            )

            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text("Server URL") },
                placeholder = { Text("https://kali-code.onrender.com") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text("Access token") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
            )

            state.error?.let {
                Text(it, color = Red, fontSize = 12.sp, modifier = Modifier.padding(top = 10.dp))
            }

            Button(
                onClick = { vm.connect(url, token) },
                colors = ButtonDefaults.buttonColors(containerColor = Accent),
                modifier = Modifier.fillMaxWidth().padding(top = 18.dp).height(48.dp),
            ) {
                if (state.status == KaliClient.Status.Connecting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        color = Color(0xFF17140F),
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text("Connect", fontWeight = FontWeight.SemiBold)
                }
            }

            Text(
                "The token is printed by the server when it starts.",
                color = Dimmer, fontSize = 11.sp,
                modifier = Modifier.padding(top = 14.dp),
            )
        }
    }
}

// --------------------------------------------------------------------- chat
@Composable
fun ChatList(vm: KaliViewModel, state: com.kalicode.app.KaliState) {
    val listState = rememberLazyListState()

    // The live prompts live outside the LazyColumn so their state is read in
    // a composable scope (LazyListScope is not @Composable).
    val permissions by vm.permissions.collectAsStateWithLifecycle()
    val questions by vm.questions.collectAsStateWithLifecycle()
    val plans by vm.plans.collectAsStateWithLifecycle()

    LaunchedEffect(state.chat.size) {
        if (state.chat.isNotEmpty()) listState.animateScrollToItem(state.chat.lastIndex)
    }

    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (state.chat.isEmpty()) {
            item {
                Column(
                    Modifier.fillMaxWidth().padding(vertical = 48.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("Ask Kali Code…", color = Dimmer, fontSize = 14.sp)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "The agent runs on your server, not on this phone.",
                        color = Dimmer, fontSize = 11.sp,
                    )
                }
            }
        }

        items(state.chat) { item ->
            when (item) {
                is ChatItem.User -> UserBubble(item.text)
                is ChatItem.Assistant -> AssistantBubble(item.text)
                is ChatItem.Thinking -> ThinkingBubble(item.text)
                is ChatItem.Error -> ErrorBubble(item.text)
                is ChatItem.Tool -> ToolCard(item.name, item.summary, item.output)
                is ChatItem.Plan -> PlanCard(item.text)
                is ChatItem.ToolItem -> ToolCard(
                    item.name, item.summary,
                    if (item.done) item.output else "",
                    done = item.done, ok = item.ok, elapsed = item.elapsed,
                )
            }
        }

        permissions.forEach { req ->
            item(key = "perm-${req.id}") {
                PermissionCard(req) { vm.answerPermission(req.id, it) }
            }
        }
        questions.forEach { req ->
            item(key = "q-${req.id}") {
                QuestionCard(req) { vm.answerQuestion(req.id, it) }
            }
        }
        plans.forEach { req ->
            item(key = "plan-${req.id}") {
                PlanApprovalCard(req) { vm.answerPlan(req.id, it) }
            }
        }
    }
}

@Composable
private fun UserBubble(text: String) {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
        SelectionContainer {
            Text(
                text,
                modifier = Modifier
                    .background(Panel2, RoundedCornerShape(14.dp))
                    .border(1.dp, Border, RoundedCornerShape(14.dp))
                    .padding(horizontal = 13.dp, vertical = 9.dp)
                    .widthIn(max = 300.dp),
                color = Fg, fontSize = 14.sp,
            )
        }
    }
}

@Composable
private fun AssistantBubble(text: String) {
    Column(Modifier.fillMaxWidth()) {
        Text("KALI", color = Accent, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        SelectionContainer {
            Text(text, color = Fg, fontSize = 14.sp, modifier = Modifier.padding(top = 3.dp))
        }
    }
}

@Composable
private fun ThinkingBubble(text: String) {
    Column(Modifier.fillMaxWidth()) {
        Text("thinking", color = Dimmer, fontSize = 10.sp, fontStyle = androidx.compose.ui.text.font.FontStyle.Italic)
        Text(text, color = Dim, fontSize = 12.sp, fontStyle = androidx.compose.ui.text.font.FontStyle.Italic)
    }
}

@Composable
private fun ErrorBubble(text: String) {
    Row(Modifier.fillMaxWidth()) {
        Box(
            Modifier
                .width(2.dp)
                .heightIn(min = 20.dp)
                .background(Red)
        )
        Text(text, color = Red, fontSize = 13.sp, modifier = Modifier.padding(start = 10.dp))
    }
}

@Composable
private fun ToolCard(name: String, summary: String, output: String,
                    done: Boolean = true, ok: Boolean = true, elapsed: Double = 0.0) {
    var expanded by remember { mutableStateOf(false) }
    Column(
        Modifier
            .fillMaxWidth()
            .background(Panel, RoundedCornerShape(10.dp))
            .border(1.dp, Border, RoundedCornerShape(10.dp))
            .padding(11.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(name, color = Purple, fontSize = 12.sp,
                 fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.width(8.dp))
            Text(
                if (!done) "running…" else if (ok) "done" else "failed",
                color = Dimmer, fontSize = 11.sp,
            )
            if (done && elapsed > 0) {
                Text(" ${elapsed}s", color = Dimmer, fontSize = 11.sp)
            }
        }
        if (summary.isNotBlank()) {
            Text(summary, color = Dim, fontSize = 11.sp,
                 fontFamily = FontFamily.Monospace, modifier = Modifier.padding(top = 4.dp))
        }
        if (output.isNotBlank()) {
            Text(
                if (expanded) output else output.take(400),
                color = Dim,
                fontSize = 10.5.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier
                    .padding(top = 6.dp)
                    .background(Bg, RoundedCornerShape(6.dp))
                    .padding(7.dp)
                    .clickable { expanded = !expanded },
            )
            if (output.length > 400) {
                Text(
                    if (expanded) "tap to collapse" else "tap to expand",
                    color = Dimmer, fontSize = 10.sp,
                    modifier = Modifier.clickable { expanded = !expanded },
                )
            }
        }
    }
}

@Composable
private fun PlanCard(text: String) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(Panel, RoundedCornerShape(10.dp))
            .border(1.dp, Blue, RoundedCornerShape(10.dp))
            .padding(11.dp)
    ) {
        Text("Plan", color = Blue, fontSize = 11.sp, fontWeight = FontWeight.Bold)
        Text(text, color = Dim, fontSize = 12.sp, modifier = Modifier.padding(top = 5.dp))
    }
}

// ---------------------------------------------------------------- permission
@Composable
private fun PermissionCard(req: PermissionRequest, onAnswer: (String) -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(Panel, RoundedCornerShape(11.dp))
            .border(1.dp, Yellow, RoundedCornerShape(11.dp))
            .padding(13.dp)
    ) {
        Text("Permission needed — ${req.tool}",
             color = Fg, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        if (req.summary.isNotBlank()) {
            Text(
                req.summary,
                color = Dim, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
                modifier = Modifier
                    .padding(top = 7.dp)
                    .fillMaxWidth()
                    .background(Bg, RoundedCornerShape(6.dp))
                    .padding(8.dp),
            )
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Button(
                onClick = { onAnswer("allow") },
                colors = ButtonDefaults.buttonColors(containerColor = Accent),
                modifier = Modifier.weight(1f),
            ) { Text("Allow", fontSize = 12.sp) }
            OutlinedButton(onClick = { onAnswer("always") }, modifier = Modifier.weight(1f)) {
                Text("Always", fontSize = 12.sp, color = Yellow)
            }
            OutlinedButton(onClick = { onAnswer("deny") }, modifier = Modifier.weight(1f)) {
                Text("Deny", fontSize = 12.sp, color = Red)
            }
        }
    }
}

@Composable
private fun QuestionCard(req: QuestionRequest, onAnswer: (String) -> Unit) {
    var custom by remember { mutableStateOf("") }
    Column(
        Modifier
            .fillMaxWidth()
            .background(Panel, RoundedCornerShape(11.dp))
            .border(1.dp, Purple, RoundedCornerShape(11.dp))
            .padding(13.dp)
    ) {
        Text("Question", color = Purple, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        Text(req.text, color = Fg, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
        req.options.forEach { opt ->
            TextButton(
                onClick = { onAnswer(opt) },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(opt, color = Accent, fontSize = 13.sp, modifier = Modifier.fillMaxWidth())
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = custom,
                onValueChange = { custom = it },
                placeholder = { Text("your answer", fontSize = 12.sp) },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            IconButton(onClick = { if (custom.isNotBlank()) onAnswer(custom) }) {
                Icon(Icons.Default.Send, "Send", tint = Accent)
            }
        }
    }
}

@Composable
private fun PlanApprovalCard(req: PlanRequest, onAnswer: (String) -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(Panel, RoundedCornerShape(11.dp))
            .border(1.dp, Blue, RoundedCornerShape(11.dp))
            .padding(13.dp)
    ) {
        Text("Plan ready for approval", color = Blue, fontSize = 12.sp,
             fontWeight = FontWeight.SemiBold)
        Text(req.plan, color = Dim, fontSize = 12.sp,
             modifier = Modifier.padding(top = 6.dp).heightIn(max = 220.dp)
                 .verticalScroll(rememberScrollState()))
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Button(
                onClick = { onAnswer("approve") },
                colors = ButtonDefaults.buttonColors(containerColor = Accent),
                modifier = Modifier.weight(1f),
            ) { Text("Approve", fontSize = 12.sp) }
            OutlinedButton(onClick = { onAnswer("reject") }, modifier = Modifier.weight(1f)) {
                Text("Reject", fontSize = 12.sp, color = Red)
            }
        }
    }
}

// ----------------------------------------------------------------- prompt
@Composable
private fun PromptBar(vm: KaliViewModel, state: com.kalicode.app.KaliState) {
    var text by remember { mutableStateOf("") }
    var modelMenu by remember { mutableStateOf(false) }
    var modeMenu by remember { mutableStateOf(false) }

    Surface(color = Panel, tonalElevation = 0.dp) {
        Column(Modifier.fillMaxWidth().padding(8.dp)) {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                placeholder = { Text("Ask Kali Code…", fontSize = 14.sp) },
                modifier = Modifier.fillMaxWidth(),
                maxLines = 6,
                shape = RoundedCornerShape(12.dp),
            )

            Row(
                Modifier.fillMaxWidth().padding(top = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box {
                    TextButton(onClick = { modelMenu = true }) {
                        Text(
                            Protocol.prettyModel(state.model),
                            color = Dim, fontSize = 11.sp,
                            maxLines = 1, overflow = TextOverflow.Ellipsis,
                        )
                    }
                    DropdownMenu(expanded = modelMenu, onDismissRequest = { modelMenu = false }) {
                        Protocol.MODELS.forEach { m ->
                            DropdownMenuItem(
                                text = { Text(Protocol.prettyModel(m), fontSize = 13.sp) },
                                onClick = { vm.setModel(m); modelMenu = false },
                            )
                        }
                    }
                }

                Box {
                    TextButton(onClick = { modeMenu = true }) {
                        Text(
                            Protocol.MODES.firstOrNull { it.first == state.permissionMode }?.second
                                ?: state.permissionMode,
                            color = Dim, fontSize = 11.sp,
                        )
                    }
                    DropdownMenu(expanded = modeMenu, onDismissRequest = { modeMenu = false }) {
                        Protocol.MODES.forEach { (id, label) ->
                            DropdownMenuItem(
                                text = { Text(label, fontSize = 13.sp) },
                                onClick = { vm.setMode(id); modeMenu = false },
                            )
                        }
                    }
                }

                Text(
                    "${state.contextPercent}%",
                    color = Dimmer, fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.padding(start = 4.dp),
                )

                Spacer(Modifier.weight(1f))

                IconButton(
                    onClick = { if (state.busy) vm.interrupt() else vm.sendPrompt(text) },
                    modifier = Modifier
                        .size(38.dp)
                        .background(if (state.busy) Red else Accent, CircleShape),
                ) {
                    Icon(
                        if (state.busy) Icons.Default.Stop else Icons.Default.Send,
                        if (state.busy) "Stop" else "Send",
                        tint = if (state.busy) Color.White else Color(0xFF17140F),
                    )
                }
            }
        }
    }
}

// ---------------------------------------------------------------- sessions
@Composable
private fun SessionSheet(vm: KaliViewModel, state: com.kalicode.app.KaliState,
                         onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Panel,
        title = { Text("Sessions", color = Fg) },
        text = {
            LazyColumn(Modifier.heightIn(max = 420.dp)) {
                items(state.sessions) { s ->
                    SessionRow(s, s.id == state.currentSession) {
                        vm.switchSession(s.id)
                        onDismiss()
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                vm.newSession()
                onDismiss()
            }) { Text("New session", color = Accent) }
        },
        dismissButton = {
            TextButton(onClick = { vm.disconnect(); onDismiss() }) {
                Text("Disconnect", color = Dim)
            }
        },
    )
}

@Composable
private fun SessionRow(s: SessionInfo, active: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .background(if (active) Panel3 else Color.Transparent, RoundedCornerShape(8.dp))
            .padding(horizontal = 8.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(7.dp)
                .background(
                    when (s.status) {
                        "running" -> Green
                        "awaiting_permission" -> Yellow
                        else -> Dimmer
                    },
                    CircleShape,
                )
        )
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(
                s.title.ifBlank { "New session" },
                color = if (active) Accent else Fg,
                fontSize = 13.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            Text(
                s.cwd,
                color = Dimmer, fontSize = 10.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
        }
        if (s.worktree) {
            Text("⑂", color = Dim, fontSize = 13.sp)
        }
    }
}
