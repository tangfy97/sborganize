import Foundation
import FoundationModels

@available(macOS 26.0, *)
@main
struct AppleBridge {
    static func emit(_ object: [String: Any]) {
        if let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([10]))
        }
    }

    static func main() async {
        let model = SystemLanguageModel.default
        switch model.availability {
        case .unavailable(let reason):
            let code: String
            switch reason {
            case .deviceNotEligible: code = "device_not_eligible"
            case .appleIntelligenceNotEnabled: code = "apple_intelligence_not_enabled"
            case .modelNotReady: code = "model_not_ready"
            @unknown default: code = "unknown_unavailability"
            }
            emit(["available": false, "reason": code])
            return
        case .available:
            break
        }
        if CommandLine.arguments.contains("--probe") {
            emit(["available": true, "provider": "apple-on-device"])
            return
        }
        do {
            let data = FileHandle.standardInput.readDataToEndOfFile()
            guard data.count <= 65536,
                  let request = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let prompt = request["prompt"] as? String,
                  let instructions = request["instructions"] as? String,
                  let targets = request["targets"] as? [String],
                  !targets.isEmpty, targets.count <= 100 else {
                emit(["error": "invalid_request"])
                return
            }
            let schema = try GenerationSchema(root: DynamicGenerationSchema(
                name: "Placement",
                properties: [
                    .init(name: "purpose_known", schema: .init(type: Bool.self)),
                    .init(name: "domain", schema: .init(type: String.self)),
                    .init(name: "region", schema: .init(name: "Region", anyOf: ["CN", "HK", "GLOBAL", "unknown"])),
                    .init(name: "confidence", schema: .init(name: "Confidence", anyOf: ["high", "medium", "low"])),
                    .init(name: "target", schema: .init(name: "Target", anyOf: targets)),
                    .init(name: "reason", schema: .init(type: String.self))
                ]), dependencies: [])
            let session = LanguageModelSession(model: model, instructions: instructions)
            var options = GenerationOptions()
            options.temperature = 0
            options.maximumResponseTokens = 256
            let response = try await session.respond(
                to: prompt, schema: schema,
                options: options
            )
            let content = response.content
            emit([
                "purpose_known": try content.value(Bool.self, forProperty: "purpose_known"),
                "domain": try content.value(String.self, forProperty: "domain"),
                "region": try content.value(String.self, forProperty: "region"),
                "confidence": try content.value(String.self, forProperty: "confidence"),
                "target": try content.value(String.self, forProperty: "target"),
                "reason": try content.value(String.self, forProperty: "reason")
            ])
        } catch {
            // No transcript or user layout in error output.
            emit(["error": "generation_failed"])
        }
    }
}
