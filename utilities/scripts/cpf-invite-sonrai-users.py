import argparse
import csv

ROLE_SRNS = {
    'viewer': 'srn:supersonrai::SonraiRole/CloudPermissionFirewallViewer',
    'admin': 'srn:supersonrai::SonraiRole/Administrator',
}

def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Script to build Sonrai User Invites ',
        epilog='''CSV file format is:\n    email_address,name\n'''
    )
    parser.add_argument('--sonrai_org', required=True, help='Sonrai org ID')
    parser.add_argument('--file', '-f', required=True, help='CSV file with user data')
    parser.add_argument('-e', '--send_email', action='store_true', help='Send invite email to user')
    parser.add_argument('-t', '--timeout', type=int, default=604800, help='Invite validity in seconds (default: 604800 = 7 days)')
    parser.add_argument('-r', '--role', required=True, help='Specifies the Sonrai role to assign to each invite. Must be one of: viewer or admin.')
    args = parser.parse_args()

    if args.role == 'viewer':
        role_srn = ROLE_SRNS['viewer']
    elif args.role == 'admin':
        role_srn = ROLE_SRNS['admin']
    else:
        raise Exception('No role provided or role not recognized. Must be one of: viewer or admin.')

    scope = f"/org/{args.sonrai_org}/*"
    timeout = args.timeout

    print("mutation inviteUser {")
    with open(args.file, newline='') as csvfile:
        reader = csv.reader(csvfile)
        for idx, row in enumerate(reader):
            if len(row) < 2:
                continue
            email, name = row[0].strip(), row[1].strip()
            print(f"  invite_{idx}: CreateSonraiInvites(")
            print(f"    input: {{")
            print(f"      email: \"{email}\"")
            print(f"      name: \"{name}\"")
            print(f"      pendingRoleAssigners: [")
            print(f"        {{ roleSrn: \"{role_srn}\", scope: \"{scope}\" }}")
            print(f"      ]")
            print(f"      ccInviterOnEmail: false")
            print(f"      sendEmail: {str(args.send_email).lower()}")
            print(f"      expiryTimeInSeconds: {timeout}")
            print(f"    }}")
            print(f"  ) {{")
            print(f"    items {{")
            print(f"      srn")
            print(f"    }}")
            print(f"  }}")
    print("}")

if __name__ == '__main__':
    main()
