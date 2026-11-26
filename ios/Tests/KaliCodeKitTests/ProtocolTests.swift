// ProtocolTests.swift - tests for the wire protocol.
//
// The protocol is the contract with `kali/serve.py`, so these tests pin
// down the parts that are easy to get wrong: unknown fields, numbers that
// arrive as strings, and the option shapes of a question.

import XCTest
@testable import KaliCodeKit

final class ProtocolTests: XCTestCase {
    func testDecodesAReadyMessage() throws {
        let json = """
        {
          "type": "ready",
          "session": "abc123",
          "model": "stepfun-ai/step-5-preview",
          "cwd": "/tmp/project",
          "version": "1.1.0",
          "sessions": [
            {
              "id": "abc123",
              "title": "Fix the build",
              "cwd": "/tmp/project",
              "model": "stepfun-ai/step-5-preview",
              "permissionMode": "default",
              "status": "idle",
              "messageCount": 3
            }
          ]
        }
        """

        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.type, "ready")
        XCTAssertEqual(msg.session, "abc123")
        XCTAssertEqual(msg.model, "stepfun-ai/step-5-preview")
        XCTAssertEqual(msg.sessions.count, 1)
        XCTAssertEqual(msg.sessions[0].title, "Fix the build")
        XCTAssertEqual(msg.sessions[0].messageCount, 3)
        XCTAssertEqual(msg.sessions[0].permissionMode, "default")
    }

    func testIgnoresUnknownFields() throws {
        let json = """
        {"type": "text", "text": "hi", "somethingNew": {"a": 1}, "n": 5}
        """
        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.type, "text")
        XCTAssertEqual(msg.text, "hi")
    }

    func testDecodesAQuestion() throws {
        let json = """
        {
          "type": "question",
          "id": "q1",
          "question": {
            "question": "Which framework?",
            "options": [
              {"label": "SwiftUI", "description": "Apple's framework"},
              {"label": "UIKit"}
            ]
          }
        }
        """
        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.type, "question")
        XCTAssertEqual(msg.question?.question, "Which framework?")
        XCTAssertEqual(msg.question?.options.count, 2)
        XCTAssertEqual(msg.question?.options[0].label, "SwiftUI")
        XCTAssertEqual(msg.question?.options[0].description, "Apple's framework")
    }

    func testDecodesAPlainStringOption() throws {
        let json = """
        {"type": "question", "id": "q2",
         "question": {"question": "Pick", "options": ["One", "Two"]}}
        """
        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.question?.options.count, 2)
        XCTAssertEqual(msg.question?.options[1].label, "Two")
    }

    func testUsageAcceptsStringsAndNumbers() throws {
        let json = """
        {"type": "done", "usage": {"prompt_tokens": 120, "completion_tokens": "45"}}
        """
        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.usage?["prompt_tokens"]?.doubleValue, 120)
        XCTAssertEqual(msg.usage?["completion_tokens"]?.doubleValue, 45)
    }

    func testDecodesAPermissionRequest() throws {
        let json = """
        {"type": "permission", "id": "p1", "name": "Bash",
         "args": {"command": "ls"}, "summary": "ls"}
        """
        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.id, "p1")
        XCTAssertEqual(msg.name, "Bash")
        XCTAssertEqual(msg.summary, "ls")
        XCTAssertEqual(msg.args?["command"]?.displayText, "ls")
    }

    func testDecodesSessionMetaWithTheObjectInMeta() throws {
        let json = """
        {"type": "session_meta", "session": "abc123",
         "meta": {"id": "abc123", "model": "minimaxai/minimax-m3.1-flash",
                  "permissionMode": "plan", "cwd": "/tmp/project"}}
        """
        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.type, "session_meta")
        XCTAssertEqual(msg.session, "abc123")
        XCTAssertEqual(msg.meta?.model, "minimaxai/minimax-m3.1-flash")
        XCTAssertEqual(msg.meta?.permissionMode, "plan")
    }

    func testDecodesSessionMetaFromTheLegacyShape() throws {
        // Older servers put the whole session object in "session".
        let json = """
        {"type": "session_meta",
         "session": {"id": "legacy1", "model": "some/model",
                     "permissionMode": "auto"}}
        """
        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.meta?.id, "legacy1")
        XCTAssertEqual(msg.meta?.model, "some/model")
        XCTAssertEqual(msg.session, "legacy1")
    }

    func testDecodesADoneMessageWithUsage() throws {
        let json = """
        {"type": "done", "text": "all set", "elapsed": 1.5,
         "session": "abc123",
         "meta": {"id": "abc123", "title": "Fix the build"},
         "usage": {"prompt_tokens": 120, "completion_tokens": 45}}
        """
        let msg = try Protocol.decoder.decode(ServerMessage.self,
                                             from: Data(json.utf8))
        XCTAssertEqual(msg.type, "done")
        XCTAssertEqual(msg.meta?.title, "Fix the build")
        XCTAssertEqual(msg.usage?["prompt_tokens"]?.doubleValue, 120)
    }

    func testEncodesAHelloMessage() throws {
        var message = ClientMessage(type: "hello")
        message.token = "secret"
        message.session = "abc"
        let data = try Protocol.encoder.encode(message)
        let json = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["type"] as? String, "hello")
        XCTAssertEqual(json["token"] as? String, "secret")
        XCTAssertEqual(json["session"] as? String, "abc")
    }

    func testPrettyModel() {
        XCTAssertEqual(Protocol.prettyModel("stepfun-ai/step-5-preview"),
                       "step 5 preview")
        XCTAssertEqual(Protocol.prettyModel("minimaxai/minimax-m3.1-flash"),
                       "minimax m3.1 flash")
        XCTAssertEqual(Protocol.prettyModel("plain"), "plain")
    }

    func testModeLabel() {
        XCTAssertEqual(Protocol.modeLabel("default"), "Manual")
        XCTAssertEqual(Protocol.modeLabel("acceptEdits"), "Accept edits")
        XCTAssertEqual(Protocol.modeLabel("plan"), "Plan")
        XCTAssertEqual(Protocol.modeLabel("auto"), "Auto")
    }
}
