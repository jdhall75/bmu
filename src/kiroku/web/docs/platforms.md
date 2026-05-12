# Platforms

A platform definition tells scrapli how to talk to a specific type of device: what the CLI prompt looks like in each mode, how to move between modes (e.g. user EXEC → privileged EXEC → config), and what to do on connect and disconnect.

## Built-in vs. custom

scrapli ships with definitions for the most common vendors. If your device matches one of these, select it on the device form and you do not need to create anything here:

- `cisco_iosxe` — Cisco IOS-XE
- `cisco_iosxr` — Cisco IOS-XR
- `cisco_nxos` — Cisco NX-OS
- `arista_eos` — Arista EOS
- `juniper_junos` — Juniper JunOS

Create a custom platform for:

- Vendors not in the list above (Nokia SRL, Adtran, MikroTik, Palo Alto, etc.)
- Devices with non-standard prompt formats or mode transitions
- Lab devices with unusual login sequences

## YAML schema overview

```yaml
prompt_pattern: "(?m)^[\\w.-]+\\s*[#>$]\\s*$"
default_mode: exec
modes:
  - name: exec
    prompt_pattern: "(?m)^[\\w.-]+>\\s*$"
    accessible_modes:
      - name: privileged_exec
        instructions:
          - type: send_input
            input: "enable"
  - name: privileged_exec
    prompt_pattern: "(?m)^[\\w.-]+#\\s*$"
    accessible_modes:
      - name: exec
        instructions:
          - type: send_input
            input: "disable"
failure_indicators:
  - "% Invalid"
  - "Error:"
on_open_instructions:
  - type: send_input
    input: "terminal length 0"
on_close_instructions:
  - type: write
    input: "exit"
```

## Key fields

| Field | Required | Description |
|-------|----------|-------------|
| `prompt_pattern` | Yes | Top-level regex matching any prompt in any mode. Used as a fallback when the mode-specific pattern doesn't match. |
| `default_mode` | Yes | The mode the device is in immediately after login. |
| `modes` | Yes | List of named modes. |
| `modes[].name` | Yes | Mode identifier referenced elsewhere in the YAML. |
| `modes[].prompt_pattern` | Yes | Regex that uniquely matches this mode's prompt. |
| `modes[].accessible_modes` | Yes | Modes reachable from this mode, and the instructions to reach them. |
| `failure_indicators` | No | Strings in command output that signal an error. |
| `on_open_instructions` | No | Sent once immediately after connecting (e.g. `terminal length 0`). |
| `on_close_instructions` | No | Sent once before disconnecting (e.g. `exit`). |

## Instruction types

| Type | Fields | Description |
|------|--------|-------------|
| `send_input` | `input: "command"` | Send a command and wait for the next prompt. |
| `enter_mode` | `requested_mode: "name"` | Transition to another mode using its defined instructions. |
| `write` | `input: "text"` | Write raw bytes without waiting for a prompt (useful for `quit` on disconnect). |

## Tips

- The `prompt_pattern` regex is matched against the full received buffer, not just one line. Use `(?m)` to enable multi-line mode and anchor with `^` and `$` to avoid false matches on banners or motd messages.
- If a device requires an enable password, define a `privileged_exec` mode with `send_input: "enable"`. Set the enable password in the credential's **Enable / secondary** field — scrapli looks it up via the `__lookup::enable` key if you reference it in the platform instructions.
- Copy the annotated example from the **New platform** form as a starting point, then adapt the prompt patterns and mode names to match your device.
- Test your platform by creating a test device and running a simple `collect` job with a single command like `show version`. If it succeeds, the platform definition is correct.
