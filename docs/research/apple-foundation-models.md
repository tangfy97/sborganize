# Apple on-device bridge

Checked on 2026-11-08: Apple silicon, macOS 27.0.1, Swift 6.4.2. The Swift helper
builds for macOS 26.0 and probes `SystemLanguageModel.default.availability`.

- [SystemLanguageModel](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel)
  is the on-device model; availability depends on system eligibility/configuration
  and model readiness.
- [Guided generation](https://developer.apple.com/documentation/foundationmodels/generating-swift-data-structures-with-guided-generation)
  supports a dynamic schema. The bridge constrains region, confidence and target
  IDs, then Python independently validates the parsed result and layout invariants.

The current machine returns `modelNotReady`, including a probe run outside the
sandbox. Inspecting System Settings showed Siri settings but no actionable model
download status in the inspected view. We did not change system language, region,
accounts, intelligence settings or security controls. The readiness cause is not
established; do not report this as a successful local inference.

The Python wrapper builds a private cached CLI executable from the bundled Swift
source, passes prompts via stdin and decodes a single JSON response. No private
prompt file is written. Timeouts or model errors keep the rules plan. The helper
never selects `PrivateCloudComputeLanguageModel` or an arbitrary hosted model.

The user declined Ollama. The local path is Apple → rules. A later user amendment
allows separate explicit OpenRouter opt-in; it is never an automatic local fallback.
