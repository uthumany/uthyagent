# AI providers

The current provider adapter speaks the OpenAI-compatible chat-completions API and reads the provider model list from `/models`. It does not include independent adapters for Google AI Studio, Hugging Face, or non-compatible APIs. Model capability metadata is shown only when the provider supplies it; UthyAgent does not infer vision support or promise free access.

## Configure a local model

Start an OpenAI-compatible local server, then configure its loopback endpoint. For example, use the endpoint and model name shown by your local Ollama, LM Studio, or vLLM setup:

```bash
uthyagent provider configure --base-url http://localhost:11434/v1 --model <model-id> --no-key
uthyagent provider test
uthyagent provider models
```

Plain HTTP is accepted only for `localhost` or an IP loopback address. Local servers may still have their own authentication or model-download requirements.

## Configure a hosted OpenAI-compatible provider

Use the provider's documented HTTPS API base URL and model ID:

```bash
uthyagent provider configure --base-url https://<provider-host>/<api-prefix> --model <model-id>
```

The command prompts for a token without echo and stores it through GNOME Secret Service using `secret-tool`, scoped to the configured provider origin. The JSON settings file contains the base URL, model ID, and timeout only. UthyAgent never attaches stored keys to loopback model requests, refuses non-loopback HTTP, and does not follow provider redirects. Choosing `--no-key` clears any key saved for that same provider origin.

For an OpenRouter configuration, the service endpoint is `https://openrouter.ai/api/v1`; `openrouter/free` can be entered as the model ID when that route is currently supported by the provider. Availability, rate limits, eligible model routing, and pricing can change. Run `provider test` and check the current provider model list; do not assume a model is permanently free.

## Data sent to a hosted provider

When a task uses hosted inference, the provider receives the task instruction, compact accessible-control names/roles/bounds, task-step summaries, and OCR text only if OCR was explicitly enabled. This alpha does not attach screenshots. Do not enter secrets or sensitive personal data into a task unless you have decided the provider may receive it.

## Limitations

- Provider configuration is CLI-only; there is no provider settings form in the GTK window.
- The connection test is a `GET /models` request; it does not prove that a task completion will work.
- Context-window and vision capabilities are not independently discovered.
- There are no built-in provider presets or account-level model menus in this alpha.
- A missing Secret Service tool prevents storing a hosted-provider key. Local no-key endpoints can still be used.
