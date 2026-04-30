# bulk-zombie-actions.py

Bulk operations for zombie (unused) identities in Sonrai that the UI doesn't support today: quarantine, unquarantine, list quarantined, and list zombies. All commands accept flexible scope inputs and auto-resolve friendly names from the cloud hierarchy.

## Prerequisites

- **Python 3.9+** and the [sonrai_api](https://github.com/sonraisecurity/sonrai-public-assets/blob/main/utilities/sonrai_api/README.md) library copied into the same directory as the script.
- Install required libraries: `pip3 install -r sonrai_api/requirements.txt`
- Sonrai API credentials configured in `sonrai_api/config.json`.

## Subcommands

```
quarantine        Quarantine zombie identities from a CSV file
unquarantine      Remove quarantine from identities in a CSV file
list-quarantined  List currently quarantined identities
list-zombies      List zombie (unused) identities
```

---

## quarantine

Reads a CSV of identities and quarantines them. Filters by last-active date using the `zombie_threshold_days` value from CPFConfigs (or a custom `--days` value).

```
python bulk-zombie-actions.py quarantine -c FILE [--scope SCOPE] [--days N] [--dryrun]
```

| Flag | Description |
|---|---|
| `-c / --csv FILE` | CSV file of identities to quarantine (required) |
| `-s / --scope SCOPE` | Only process identities at this scope |
| `--days N` | Only quarantine identities unused for >= N days. Defaults to `zombie_threshold_days` from CPFConfigs |
| `-n / --dryrun` | Preview what would be quarantined without executing |

**Examples**

```bash
# Quarantine all zombies in the CSV using the configured threshold
python bulk-zombie-actions.py quarantine -c zombies.csv

# Quarantine only identities unused for 180+ days
python bulk-zombie-actions.py quarantine -c zombies.csv --days 180

# Scope to a single account and dry run first
python bulk-zombie-actions.py quarantine -c zombies.csv --scope 471112776591 --dryrun
```

---

## unquarantine

Reads a CSV of identities and removes them from quarantine.

```
python bulk-zombie-actions.py unquarantine -c FILE [--scope SCOPE] [--dryrun]
```

| Flag | Description |
|---|---|
| `-c / --csv FILE` | CSV file of identities to unquarantine (required) |
| `-s / --scope SCOPE` | Only process identities at this scope |
| `-n / --dryrun` | Preview what would be unquarantined without executing |

**Example**

```bash
python bulk-zombie-actions.py unquarantine -c quarantined.csv --dryrun
```

---

## list-quarantined

Lists identities currently in quarantine. Displays a table to stdout and optionally exports to CSV.

```
python bulk-zombie-actions.py list-quarantined [--scope SCOPE] [--days N] [--output FILE]
```

| Flag | Description |
|---|---|
| `-s / --scope SCOPE` | Filter to identities at this scope |
| `--days N` | Only show identities that have been quarantined for >= N days |
| `-o / --output FILE` | Write results to a CSV file |

**Examples**

```bash
# List all quarantined identities
python bulk-zombie-actions.py list-quarantined

# List identities quarantined for 30+ days in a specific org
python bulk-zombie-actions.py list-quarantined --scope aws/r-bitm --days 30

# Export to CSV for use with unquarantine
python bulk-zombie-actions.py list-quarantined -o quarantined.csv
```

**Table columns:** NAME, ACCOUNT, SCOPE (friendly name), QUARANTINED ON, LAST USED (human-readable age)

---

## list-zombies

Lists zombie (unused) identities from the Sonrai CPF engine. Displays a table to stdout and optionally exports to CSV.

```
python bulk-zombie-actions.py list-zombies [--scope SCOPE] [--days N] [--output FILE]
```

| Flag | Description |
|---|---|
| `-s / --scope SCOPE` | Filter to identities at this scope |
| `--days N` | Only show identities unused for >= N days. Defaults to `zombie_threshold_days` from CPFConfigs |
| `-o / --output FILE` | Write results to a CSV file |

If `--scope` is not provided, the script automatically queries all org roots found in the cloud hierarchy.

**Examples**

```bash
# List all zombies across all orgs (threshold from CPFConfigs)
python bulk-zombie-actions.py list-zombies

# List zombies unused for 90+ days in a specific org
python bulk-zombie-actions.py list-zombies --scope aws/r-bitm --days 90

# Export and pipe into quarantine
python bulk-zombie-actions.py list-zombies -o zombies-out.csv
python bulk-zombie-actions.py quarantine -c zombies-out.csv --dryrun
```

**Table columns:** NAME, ACCOUNT, SCOPE (friendly name), LAST ACTIVE (human-readable age)

---

## Scope Resolution

All `--scope` values are resolved automatically. Accepted formats:

| Input | Example |
|---|---|
| Full scope string | `aws/r-bitm/ou-bitm-xxx/123456789012` |
| Org root ID | `r-bitm` or `aws/r-bitm` |
| OU ID | `ou-bitm-hjr6a0li` |
| 12-digit account number | `471112776591` |
| Account or OU name | `"My Production Account"` |

If a name matches multiple scopes, the script lists the candidates and exits — use a more specific value to disambiguate.

---

## CSV Format

### Input (quarantine / unquarantine)

```
Scope,Identity,Last active
aws/r-bitm/ou-bitm-xxx/123456789012,arn:aws:iam::123456789012:role/MyRole,Unused
aws/r-bitm/ou-bitm-xxx/123456789012,arn:aws:iam::123456789012:role/OtherRole,2025-08-01T00:00:00.000Z
```

- **Scope** — may be blank; the script derives it from the account number in the ARN, or performs a global search across all orgs if Identity is also a bare name
- **Identity** — full ARN preferred; a bare name (e.g. `MyRole`) triggers a lookup — first in `UnusedIdentities` (at the resolved scope), then in `IdentitiesInQuarantine` (for identities already quarantined)
- **Last active** — ISO 8601 datetime or `Unused`; used for `--days` filtering on quarantine

The header row is optional. Column order matters when there is no header.

### Output (list-quarantined / list-zombies `--output`)

```
Scope,Scope (friendly),Identity,Last active,Last active (readable),quarantinedOn,quarantinedBy
```

This output is directly usable as input for `quarantine` or `unquarantine` — extra columns are ignored by the loader.

---

## Workflow Example: Full Zombie Remediation Cycle

```bash
# 1. Preview all zombies across all orgs
python bulk-zombie-actions.py list-zombies

# 2. Export zombies unused for 90+ days to a file
python bulk-zombie-actions.py list-zombies --days 90 -o to-quarantine.csv

# 3. Dry run the quarantine
python bulk-zombie-actions.py quarantine -c to-quarantine.csv --dryrun

# 4. Quarantine
python bulk-zombie-actions.py quarantine -c to-quarantine.csv

# 5. Later: review what's been quarantined for over a year for manual review and deletion
python bulk-zombie-actions.py list-quarantined -o quarantined.csv --days 365


```
