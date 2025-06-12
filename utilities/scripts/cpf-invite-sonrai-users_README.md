# cpf-invite-sonrai-users.py

A utility script to generate Sonrai Security user invite GraphQL mutations from a CSV file. This script is designed to help automate the process of inviting users to a Sonrai organization with specific roles and scopes.

## Features
- Reads a CSV file with user email and name.
- Supports three roles: Viewer, Administrator, and Approver.
- Lets you specify the Sonrai organization ID and invite validity period.
- Outputs GraphQL mutations for each user in the CSV.

## CSV Format
The input CSV file should have the following format (no header):

```
user1@example.com,User One
user2@example.com,User Two
```

## Usage

```sh
python cpf-invite-sonrai-users.py --sonrai_org <ORG_ID> --file <users.csv> --role <viewer|admin> [--send_email] [--timeout <seconds>]
```

### Required Arguments
- `--sonrai_org`      Sonrai organization ID (e.g., 1234567890abcdef)
- `--file`           Path to the CSV file with user data
- `--role`           Specifies the Sonrai role to assign to each invite. Must be one of: viewer, admin.

### Optional Arguments
- `--send_email`     Send invite email to user (default: False)
- `--timeout`        Invite validity in seconds (default: 604800 = 7 days)

## Example

```
python cpf-invite-sonrai-users.py --sonrai_org 1234567890abcdef --file users.csv --role viewer --send_email
```

This will generate GraphQL mutations to invite each user in `users.csv` as a Viewer, sending them an invite email, with the invite valid for 7 days.

## Output
The script prints a GraphQL mutation block to standard output in the following format:

```
mutation inviteUser {
  invite_0: CreateSonraiInvites(
    input: {
      email: "user1@example.com"
      name: "User One"
      pendingRoleAssigners: [
        {
          roleSrn: "srn:supersonrai::SonraiRole/CloudPermissionFirewallViewer"
          scope: "/org/1234567890abcdef/*"
        }
      ]
      ccInviterOnEmail: false
      sendEmail: true
      expiryTimeInSeconds: 604800
    }
  ) {
    items {
      srn
    }
  }
  ...
}
```

You can copy and paste this into your Sonrai GraphQL API interface.

## License
MIT
