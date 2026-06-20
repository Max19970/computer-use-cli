# Computer Use MCP for ChatGPT — design

Date: 2026-06-20

## Goal

Expose the existing Windows `computer-use-cli` to ChatGPT as a private MCP app through a dedicated OpenAI Secure MCP Tunnel.

The integration must preserve the CLI safety policies, keep the local server private, return screenshots directly to ChatGPT, and make every computer-changing invocation subject to ChatGPT confirmation.

## Approved user experience

- The app is named `Computer Use MCP`.
- It exposes exactly two tools: `observe` and `act`.
- `observe` captures the primary monitor by default and returns:
  - the screenshot as MCP image content;
  - compact structured state for the cursor, active window, screen, top-level windows, and optional UI Automation data.
- `act` accepts exactly one structured CLI action per invocation.
- After each `act`, the model is instructed to call `observe` again before deciding on the next action.
- Every `act` invocation is marked as a write/destructive operation. During ChatGPT app setup, its Action control must be set to always require confirmation.
- At startup the user chooses one fixed access mode from an interactive menu:
  1. `observe-only`
  2. `guarded`
  3. `permissive`
- Changing mode requires stopping and restarting the launcher.

## Architecture

The MCP server is implemented inside the existing Python package and calls `computer_use_cli` library functions directly.

```text
ChatGPT
  -> dedicated Secure MCP Tunnel endpoint
  -> OpenAI tunnel-client (outbound HTTPS)
  -> local streaming HTTP MCP server
  -> computer_use_cli.observe / actions / policy
  -> interactive Windows desktop session
```

No generic shell, subprocess, or arbitrary CLI command proxy is exposed. This avoids shell injection and preserves typed action handling.

The server must run in the same logged-in, unlocked Windows session as the desktop it controls. It cannot operate a locked desktop or a disconnected non-interactive session reliably.

## Tool contract

### `observe`

Purpose: read the current desktop state before acting or after verifying an action.

Suggested inputs:

- `include_windows: bool = true`
- `include_uia: bool = false`
- `uia_depth: int = 1`, bounded to a small safe range
- `uia_title: string | null = null`

Server behavior:

- Select the primary physical monitor, not MSS monitor `0` (the full virtual desktop).
- Write the temporary screenshot only inside a server-owned runtime directory.
- Call the existing `observe_state` function.
- Read the generated image, return it as standard MCP image content, then remove or rotate temporary artifacts.
- Return structured state without depending on the local file path being meaningful to ChatGPT.
- Degrade partially when window/UIA collection fails, matching current `observe_state` behavior.

Metadata:

- `readOnlyHint: true`
- `destructiveHint: false`
- `idempotentHint: true`
- `openWorldHint: false`

### `act`

Purpose: execute one existing structured `computer-use-cli` action.

Input:

- `action`: one JSON object containing a string `type` field and the parameters for that action.
- `dry_run: bool = false`

Server behavior:

- Reject arrays, batches, sequences, and objects without a valid `type`.
- Reject unsupported action types before dispatch.
- Use the policy selected at server startup; callers cannot choose or override it.
- Build the policy with `preset_policy(selected_mode)` so `COMPUTER_USE_POLICY` cannot silently override the interactive selection.
- Call the existing `run_action` directly.
- Return the selected mode, action type, dry-run status, and structured result.
- Never automatically execute a second action.

Metadata:

- `readOnlyHint: false`
- `destructiveHint: true`
- `idempotentHint: false`
- `openWorldHint: true`

The server instruction begins with the required loop:

> Call `observe` before the first action. Call `act` for exactly one action only after user confirmation. Then call `observe` again and verify the result.

ChatGPT controls the confirmation UI. MCP metadata cannot independently prove that a human clicked a confirmation button, so setup must also configure the `act` action as “Always confirm” in ChatGPT.

## Access modes

The access mode is immutable for one server process.

### `observe-only`

- Uses the existing `observe-only` preset.
- Mouse, keyboard, text input, and window focus mutations are blocked.
- Read-only action types remain available through `act`, although normal model guidance should prefer `observe`.

### `guarded`

- Uses the existing `guarded` preset.
- Keeps denied sensitive-window title checks.
- Keeps limits for click count, scrolling, text length, and sleep duration.
- Keeps the `uiaClick` dry-run requirement.

### `permissive`

- Uses the existing `permissive` preset.
- Preserves direct CLI behavior with PyAutoGUI fail-safe still enabled.
- The launcher displays a prominent warning before starting.

All modes can expose visible screen contents through `observe`; the launcher must warn the user to close or hide sensitive information before connecting ChatGPT.

## Startup and shutdown

A PowerShell launcher provides the only normal startup path:

1. Show the three-mode menu.
2. Display the selected mode and security warning.
3. Start the local MCP server with that immutable mode.
4. Wait for its health endpoint.
5. Start the dedicated Secure MCP Tunnel client.
6. On Ctrl+C or failure, stop both processes and remove temporary runtime files.

The launcher may start the local helper process hidden, but remains visible itself so the user can see status and stop the integration.

Secrets are loaded from ignored local environment files or environment variables. No API key, OAuth secret, tunnel credential, or token is committed to Git.

## HTTP, authentication, and tunnel

- Local MCP transport: streaming HTTP.
- Local bind address: loopback only.
- Remote exposure: a new dedicated OpenAI Secure MCP Tunnel; no inbound firewall port.
- ChatGPT authentication: OAuth, using the same proven local authorization/resource-server pattern as the already working MCP integrations.
- OAuth clients and issued-token state persist across restarts where required by ChatGPT.
- The advertised protected-resource audience must exactly match the hosted tunnel MCP endpoint.
- The launcher enables plaintext HTTP only for the loopback hop required by the tunnel client; the external connection remains HTTPS.

## Error handling

- Policy denials return clear MCP tool errors without retrying or weakening policy.
- PyAutoGUI fail-safe remains enabled and is reported as an interrupted action.
- Invalid schemas and unsupported action types fail before desktop interaction.
- `observe` can return partial structured state if optional window/UIA data fails.
- Server logs exclude screenshot bytes, typed text, OAuth tokens, and other secrets by default.

## Testing

Automated tests:

- action input accepts one object and rejects batches;
- startup mode is immutable and cannot be overridden by tool input or environment;
- each preset allows/blocks representative actions as expected;
- `observe` returns both image content and structured state;
- tool annotations identify `observe` as read-only and `act` as destructive;
- temporary screenshots remain inside the runtime directory;
- streaming HTTP initialization, tool listing, and tool calls work with an MCP client;
- OAuth discovery and protected-resource metadata advertise exact tunnel URLs.

Manual smoke test:

1. Start in `observe-only`; verify screenshot delivery and a blocked click.
2. Start in `guarded`; verify ChatGPT confirmation, one harmless action, and post-action observation.
3. Verify a sensitive-window mutation is blocked.
4. Optionally start in `permissive` and perform one harmless action.
5. Stop the launcher and verify the tunnel and local server both exit.

## Documentation deliverables

- README section for MCP installation, startup, access modes, and safety.
- Exact ChatGPT custom app creation steps.
- Instructions to set `act` to always confirm.
- Troubleshooting for locked desktops, stale app tool metadata, OAuth failures, screenshots, and tunnel connectivity.

## Sources

- OpenAI, “Build your MCP server”: https://developers.openai.com/apps-sdk/build/mcp-server
- OpenAI, “ChatGPT Developer mode”: https://developers.openai.com/api/docs/guides/developer-mode
- OpenAI, “Secure MCP Tunnel”: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- OpenAI Help Center, “Developer mode and MCP apps in ChatGPT”: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta
