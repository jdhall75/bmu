# Credentials

Credentials store the login information Kiroku uses to connect to devices. They are referenced by groups and individual devices rather than stored inline, so a single credential can be shared across many devices and updated in one place.

## Credential providers

| Provider | How secrets are stored |
|----------|----------------------|
| **local** | Encrypted with Fernet (AES-128) and stored in the database. The encryption key is derived from `KIROKU_SECRET_KEY` in your environment. |
| **vault** | Secrets live in HashiCorp Vault. The **Reference** field holds the Vault path (e.g. `secret/kiroku/cisco-edge`). |
| **bitwarden** | Secrets live in a Bitwarden organisation. The **Reference** field holds the item ID. |

For `vault` and `bitwarden` providers, Kiroku resolves the credential at job-dispatch time — it never stores the actual secret in its own database.

## Fields

| Field | Notes |
|-------|-------|
| **Name** | A human-readable label. Used in group and device forms to pick this credential. |
| **Description** | Optional. Helps distinguish credentials with similar names. |
| **Provider** | `local`, `vault`, or `bitwarden`. |
| **Username** | Stored in plain text as a convenience for the UI — it is not sensitive. For `vault`/`bitwarden` the username is pulled from the external secret at run time; what you enter here is informational only. |
| **Password** | Local provider only. Leave blank on edit to keep the existing value. |
| **Enable / secondary** | Local provider only. Used for devices that require a privilege-escalation password (e.g. Cisco `enable`). Leave blank if not needed. |
| **Reference** | Vault path or Bitwarden item ID. Not used for local credentials. |
| **Default fallback** | Check this to make the credential the system-wide fallback. |

## Credential resolution order

When a job runs against a device, Kiroku looks for a credential in this order, using the first one it finds:

1. **Device credential override** — set on the individual device form.
2. **Group default credential** — set on the group the device is being targeted through.
3. **System default credential** — the one with **Default fallback** checked.

If none of the three is available the run is immediately marked **failed** with the error "no credential available".

## The default fallback

At most one credential can be marked as the default at a time. Checking the box on a new credential automatically clears it from the previous default.

The default is most useful in:

- **Lab environments** where all devices share one account.
- **Bootstrapping** — mark a temporary credential as default while you're bulk-importing devices, then switch to per-group credentials once the inventory is settled.

## Tips

- Rotate local credentials by editing the credential and entering a new password. All devices that reference it immediately pick up the new value on the next run — there is nothing else to update.
- For production networks, prefer per-group credentials over the system default. It gives you a clear audit trail when you need to roll one site's password without touching others.
- Vault and Bitwarden credentials are resolved at dispatch time, so rotating secrets in those systems takes effect on the very next job run.
