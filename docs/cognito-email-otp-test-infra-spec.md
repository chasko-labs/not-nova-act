# cognito email otp test infrastructure spec

status: specification only

this document defines the aws resources required by `cognito_email_login_tool`

## receipt path

| resource             | value                                             |
| -------------------- | ------------------------------------------------- |
| aws account          | `211125425201`                                    |
| region               | `us-west-2`                                       |
| ses receipt rule set | `not-nova-act-inbound`                            |
| receipt rule         | `not-nova-act-cognito-otp`                        |
| recipient            | `not-nova-act-otp@clouddelnorte.org`              |
| bucket               | `not-nova-act-ses-inbound-211125425201-us-west-2` |
| object prefix        | `cognito-otp/`                                    |
| rule action          | s3 action with `scan_enabled = true`              |
| object retention     | seven days or less                                |

create the rule enabled, place it first in the active receipt rule set, route only
the listed recipient to the s3 action, preserve the raw message, then add an s3
bucket policy allowing the ses service principal to put objects only under the
prefix with source account `211125425201` and the receipt rule set arn as
conditions

configure the domain mx record for the ses inbound endpoint in `us-west-2`
without changing any personal mailbox route

## cognito test user

| setting         | value                                            |
| --------------- | ------------------------------------------------ |
| user pool       | `us-west-2_9iBCSH8P0`                            |
| app client      | `7ssbt4gqkg4lgl1vre4ofgb0at`                     |
| username        | `not-nova-act-otp@clouddelnorte.org`             |
| email           | `not-nova-act-otp@clouddelnorte.org`             |
| email verified  | `true`                                           |
| user enabled    | `true`                                           |
| welcome message | suppressed                                       |
| auth path       | `USER_AUTH` with `PREFERRED_CHALLENGE=EMAIL_OTP` |

create or update the user through a secure operator path, keep any password
outside this repository, never use the mom alias, and never use a personal gmail
address

confirm the user pool client permits `USER_AUTH` plus `EMAIL_OTP` before live
verification

## tool read policy

attach this least-privilege policy to the local operator role or ci workload
role used by the tool

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOtpPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::not-nova-act-ses-inbound-211125425201-us-west-2",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["cognito-otp", "cognito-otp/*"]
        }
      }
    },
    {
      "Sid": "ReadOtpMessages",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::not-nova-act-ses-inbound-211125425201-us-west-2/cognito-otp/*"
    }
  ]
}
```

no ses api permission is required by the tool because the browser triggers
cognito and ses delivers the message

## verification sequence

- send a test message through the browser flow with the dedicated user
- verify a new raw object arrives under `cognito-otp/`
- verify the reader can list, get, recipient-filter, and parse the eight-digit code
- verify a resend creates a later object and the reader ignores the baseline object
- verify the browser lands on `/mom/` with a non-expired `localStorage` `app.idToken`

no resource in this specification is provisioned by this pull request
