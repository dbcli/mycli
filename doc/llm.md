# Using the \llm Command (AI-assisted SQL)

The `\llm` special command lets you ask natural-language questions and get SQL proposed for you. It uses the open‑source `llm` CLI under the hood and enriches your prompt with database context (schema and one sample row per table) so answers can include runnable SQL.

Alias: `\ai` works the same as `\llm`.

---

## Quick Start

1) Configure your API key (only needed for remote providers like OpenAI):

```text
\llm keys set openai
```

2) Ask a question. The response’s SQL (inside a ```sql fenced block) is extracted and pre-filled at the prompt:

```text
World> \llm "Capital of India?"
-- Answer text from the model...
-- ```sql
-- SELECT ...;
-- ```
-- Your prompt is prefilled with the SQL above.
```

You can now hit Enter to run, or edit the query first.

---

## What Context Is Sent

When you ask a plain question via `\llm "..."`, mycli:
- Sends your question.
- Adds your current database schema: table names with column types.
- Adds one sample row (if available) from each table.

This helps the model propose SQL that fits your schema. Follow‑ups using `-c` continue the same conversation and do not re-send the DB context (see “Continue Conversation (-c)”).

Note: Context is gathered from the current connection. If you are not connected, using contextual mode will fail — connect first.

---

## Using `llm` Subcommands from mycli

You can run any `llm` CLI subcommand by prefixing it with `\llm` inside mycli. Examples:

- List models:
  ```text
  \llm models
  ```
- Set the default model:
  ```text
  \llm models default gpt-5
  ```
- Set provider API key:
  ```text
  \llm keys set openai
  ```
- Install a plugin (e.g., local models via Ollama):
  ```text
  \llm install llm-ollama
  ```
  After installing or uninstalling plugins, mycli will restart to pick up new commands.

Tab completion works for `\llm` subcommands, and even for model IDs under `models default`.

Aside: <https://ollama.com/> for using local models.

---

## Ask Questions With DB Context (default)

Ask your question in quotes. mycli sends database context and extracts a SQL block if present.

```text
World> \llm "Most visited urls?"
```

Behavior:
- Response is printed in the output pane.
- If the response contains a ```sql fenced block, mycli extracts the SQL and pre-fills it at your prompt.

---

## Continue Conversation (-c)

Use `-c` to ask a follow‑up that continues the previous conversation with the model. This does not re-send the DB context; it relies on the ongoing thread.

```text
World> \llm "Top 10 customers by spend"
-- model returns analysis and a ```sql block; SQL is prefilled
World> \llm -c "Now include each customer's email and order count"
```

Behavior:
- Continues the last conversation in the `llm` history.
- Database context is not re-sent on follow‑ups.
- If the response includes a ```sql block, the SQL is pre-filled at your prompt.


---

## Examples

- List available models:
  ```text
  World> \llm models
  ```

- Change default model:
  ```text
  World> \llm models default llama3
  ```

- Set API key (for providers that require it):
  ```text
  World> \llm keys set openai
  ```

- Ask a question with context:
  ```text
  World> \llm "Capital of India?"
  ```

- Use a local model (after installing a plugin such as `llm-ollama`):
  ```text
  World> \llm install llm-ollama
  World> \llm models default llama3
  World> \llm "Top 10 customers by spend"
  ```

See: <https://ollama.com/> for details.

---

## Customize the Prompt Template

mycli uses a saved `llm` template named `mycli-llm-template` for contextual questions. You can view or edit it:

```text
World> \llm templates edit mycli-llm-template
```

Tip: After first use, mycli ensures this template exists. To just view it without editing, use:

```text
World> \llm templates show mycli-llm-template
```

---

## Troubleshooting

- No SQL pre-fill: Ensure the model’s response includes a ```sql fenced block. The built‑in prompt encourages this, but some models may omit it; try asking the model to include SQL in a ```sql block.
- Not connected to a database: Contextual questions require a live connection. Connect first. Follow‑ups with `-c` only help after a successful contextual call.
- Plugin changes not recognized: After `\llm install` or `\llm uninstall`, mycli restarts automatically to load new commands.
- Provider/API issues: Use `\llm keys list` and `\llm keys set <provider>` to check credentials. Use `\llm models` to confirm available models.

---

## Notes and Safety

- Data sent: Contextual questions send schema (table/column names and types) and a single sample row per table. Review your data sensitivity policies before using remote models; prefer local models (such as ollama) if needed.
- Help: Running `\llm` with no arguments shows a short usage message.

---

## Learn More

- `llm` project docs: https://llm.datasette.io/
- `llm` plugin directory: https://llm.datasette.io/en/stable/plugins/directory.html
