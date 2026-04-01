# Creating a Custom IQE User for Stage Environment Testing

> **Author:** Insights HBI QE Team
> **Last Updated:** 2026-04-01
> **Purpose:** Enable isolated testing in Stage environment without affecting other teams

---

## Why Create a Custom User?

The existing IQE test users (like `insights_inventory_qe`, `insights_qa`) are **shared across all Red Hat services**. When you use these shared users:

- ❌ Your test data mixes with other teams' test data
- ❌ Your actions (creating/deleting hosts, toggling feature flags) affect other services
- ❌ You cannot safely enable/disable feature flags without impacting others
- ❌ Debugging becomes difficult when multiple teams use the same org_id

**Solution:** Create your own dedicated user with a unique Org ID for isolated testing.

---

## Placeholder Reference

This guide uses placeholder constants for server addresses and sensitive information. You **must** replace these with actual values from your team or internal Red Hat documentation:

| Placeholder | What It Represents | Where to Get Real Value |
|------------|-------------------|------------------------|
| `ETHEL_SERVER_ADDRESS` | Ethel user management URL | Ask your QE team or check internal wiki |
| `ACCESS_STAGE_SERVER_ADDRESS` | Stage access management API | Ask your QE team or check internal wiki |
| `API_ACCESS_STAGE_SERVER_ADDRESS` | Stage API hostname | Ask your QE team or check internal wiki |
| `MTLS_CONSOLE_SERVER_ADDRESS` | mTLS console for RBAC | Ask your QE team or check internal wiki |
| `CONSOLE_STAGE_SERVER_ADDRESS` | Stage console URL | Ask your QE team or check internal wiki |
| `YOUR_EMAIL_ADDRESS` | Your Red Hat email | Your actual Red Hat email |
| `your-password-here` | Secure password | Create a strong, unique password |
| `YOUR_REFRESH_TOKEN_HERE` | Authentication token | Generated in Step 3 from access management |

> ⚠️ **Security Notice**:
> - Never use placeholder values in real configurations
> - Do not share server addresses publicly or in unsecured documentation
> - Contact your team lead or QE team for actual server addresses

---

## Prerequisites

- Access to Ethel: https://ETHEL_SERVER_ADDRESS/#create
- Red Hat SSO account with permissions to create users
- Access to Stage environment

---

## Step 1: Create an Admin User in Ethel

Ethel is the user management system for Red Hat environments.

### 1.1 Navigate to Ethel

Go to: **https://ETHEL_SERVER_ADDRESS/#create**

### 1.2 Create a New Admin User

Fill in the form with these details:

| Field | Value | Example |
|-------|-------|---------|
| **Username** | Choose a unique username ending in `-admin` | `your-username-admin` |
| **Email** | Your Red Hat email | `YOUR_EMAIL_ADDRESS` |
| **First Name** | Your first name | `John` |
| **Last Name** | Your last name | `Doe` |
| **Account Type** | Select "Admin" | Admin |

**Important:**
- Use a descriptive username that indicates purpose (e.g., `hbi-yourname-admin`, `hbi-feature-test-admin`)
- The `-admin` suffix helps identify admin accounts
- Creating this user will **automatically generate a new Org ID**

### 1.3 Save the Org ID

After creating the admin user, Ethel will display the **Org ID**.

**CRITICAL:** Write down this Org ID immediately!

Example:
```
Org ID: 1234567
Account Number: 7654321
```

This Org ID is your **isolated testing environment**. All hosts, feature flags, and data under this Org ID are separate from other teams.

---

## Step 2: Create a Regular User for Testing

Now create a non-admin user that will be used by IQE for actual testing.

### 2.1 Add User to the New Org

In Ethel, while still viewing your admin user:

1. Click "Add User to Organization"
2. Fill in the details:

| Field | Value | Example |
|-------|-------------|---------|
| **Username** | Descriptive test username | `your-test-user-01` |
| **Email** | Your Red Hat email | `YOUR_EMAIL_ADDRESS` |
| **First Name** | Descriptive name | `Test` |
| **Last Name** | Descriptive name | `User One` |
| **Account Type** | Select "User" (not Admin) | User |
| **Org ID** | Use the Org ID from Step 1.3 | `1234567` |

### 2.2 Set Password

After creating the user, set a password. Choose a secure password you'll remember.

Example password format: `YourPassword123!`

**Save this information:**
```
Username: your-test-user-01
Password: your-password-here
Org ID: 1234567
Account Number: 7654321
```

---

## Step 3: Obtain Refresh Token

The IQE framework uses refresh tokens for authentication to Stage environment.

### 3.1 Login to Stage Access Management API

1. Go to: **https://ACCESS_STAGE_SERVER_ADDRESS/management/api**
2. Login with your newly created user (`your-test-user-01`)
3. Complete any 2FA/MFA prompts if required

### 3.2 Generate Refresh Token

Once logged in to the API management page:

1. Navigate to the **"Generate Token"** or **"API Tokens"** section
2. Click **"Generate New Token"** or **"Create Token"**
3. Set token expiration (recommended: 90 days)
4. Click **"Generate"**
5. Copy the generated refresh token immediately

**The token will look like this:**
```
YOUR_REFRESH_TOKEN_HERE
```

**Important:**
- Refresh tokens are long (500+ characters)
- They expire based on the duration you set (usually 30-90 days)
- You'll need to regenerate this token when it expires
- **Store securely** - treat it like a password

---

## Step 4: Create `host_inventory.local.yaml`

This file stores your custom user configuration locally and is **excluded from git** (never committed).

### 4.1 File Location

Create the file at:
```
iqe-host-inventory-plugin/iqe_host_inventory/conf/host_inventory.local.yaml
```

### 4.2 File Structure

```yaml
stage: &stage
  legacy_hostname: "API_ACCESS_STAGE_SERVER_ADDRESS"
  turnpike_base_url: "https://MTLS_CONSOLE_SERVER_ADDRESS/api/rbac"
  default_user: your_test_user_01
  org_admin_user: your_test_user_01
  secondary_user: your_test_user_01
  frontend_user: your_test_user_01
  users:
    your_test_user_01:
      auth:
        username: "your-test-user-01"
        password: "your-password-here"
        refresh_token: "YOUR_REFRESH_TOKEN_HERE"
      identity:
        account_number: "7654321"
        org_id: "1234567"

stage_proxy: *stage
```

> ⚠️ **Important**: Replace ALL placeholder values above with your actual credentials:
> - Server addresses: Get from your QE team (see Placeholder Reference section)
> - `username`: Your actual Ethel username (with hyphens)
> - `password`: Your actual password from Step 2
> - `refresh_token`: Your actual token from Step 3
> - `account_number` and `org_id`: Your actual values from Ethel
>
> Never commit this file to git - it's protected by `.gitignore`.

### 4.3 Field Explanations

| Field | Description | Example Value |
|-------|-------------|---------------|
| `default_user` | Primary user for IQE commands | `your_test_user_01` |
| `username` | Username from Ethel (note: hyphens!) | `your-test-user-01` |
| `password` | Password you set in Ethel | `your-password-here` |
| `refresh_token` | Token from Step 3.2 | `YOUR_REFRESH_TOKEN_HERE` |
| `account_number` | From Ethel | `7654321` |
| `org_id` | From Ethel (Step 1.3) | `1234567` |
| `stage_proxy: *stage` | Creates alias for convenience | (YAML anchor) |

**IMPORTANT:** Notice the user key format:
- In `users:` section use **underscores**: `your_test_user_01`
- In `auth.username:` use **hyphens**: `your-test-user-01`

This matches how Ethel creates usernames vs. how IQE references them internally.

### 4.4 Verify .gitignore Protection

Ensure `.gitignore` excludes this file:

```bash
# Check if the pattern exists
grep "host_inventory.local.yaml" .gitignore
```

Expected output:
```
iqe-host-inventory-plugin/**/host_inventory.local.yaml
```

If not present, add it to `.gitignore`:
```bash
echo "iqe-host-inventory-plugin/**/host_inventory.local.yaml" >> .gitignore
```

**Why?** This file contains credentials and should NEVER be committed to git.

---

## Step 5: Test Your Configuration

### 5.1 Create Test Hosts

Run the IQE command to create hosts in Stage:

```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory create-hosts \
  -n 10 \
  --user your_test_user_01
```

**Expected behavior:**
- Browser may open for authentication (first time only)
- Creates 10 hosts under your Org ID (`1234567`)
- Hosts are isolated from other teams

### 5.2 Verify Hosts Were Created

```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory cleanup \
  --user your_test_user_01 \
  --interval 0 \
  --unit days \
  --dry-run
```

This shows all hosts in your org without deleting them.

### 5.3 Cleanup Test Hosts

When done testing:

```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory cleanup \
  --user your_test_user_01 \
  --interval 0 \
  --unit days \
  -y
```

---

## Advanced: Feature Flag Management

One major benefit of having your own Org ID is **independent feature flag control**.

### Enable Feature Flags for Your Org Only

Contact the Unleash/Feature Flag team to enable flags specifically for your Org ID.

**Example request:**
```
Subject: Enable feature flag for isolated testing

Hi Feature Flag team,

Please enable the following feature flag for isolated testing:

Flag: hbi.api.kessel-groups
Org ID: 1234567
Reason: Testing RBAC v2 migration without affecting other teams
Duration: 30 days (or until further notice)

Thanks,
[Your Name]
```

This allows you to:
- ✅ Test feature flags without impacting production-like testing by other teams
- ✅ Toggle flags on/off independently
- ✅ Validate behavior in both enabled and disabled states
- ✅ Debug issues in isolation

---

## Troubleshooting

### Issue: "User not found in host_inventory config"

**Cause:** The user name in `--user` doesn't match the key in `host_inventory.local.yaml`.

**Solution:**
- Verify the user key matches exactly: `your_test_user_01` (underscores, not hyphens)
- Check the file location: `iqe-host-inventory-plugin/iqe_host_inventory/conf/host_inventory.local.yaml`
- The format is: `--user your_test_user_01` (matches the key under `users:`)

### Issue: "Authentication failed" or "401 Unauthorized"

**Cause:** Refresh token expired or password is incorrect.

**Solution:**
1. Re-login to https://ACCESS_STAGE_SERVER_ADDRESS/management/api with your user
2. Generate a new refresh token (Step 3.2)
3. Update `host_inventory.local.yaml` with the new token

### Issue: "Org ID mismatch" or hosts appear under wrong org

**Cause:** `org_id` in config doesn't match Ethel.

**Solution:**
1. Verify Org ID in Ethel: https://ETHEL_SERVER_ADDRESS
2. Update `host_inventory.local.yaml` with correct `org_id`

### Issue: Hosts created but visible to other teams

**Cause:** Using shared Org ID instead of your custom one.

**Solution:**
- Double-check you created a NEW user in Ethel (not reusing existing)
- Verify the Org ID in your config matches your Ethel-created Org ID
- Ensure you're using `--user your_test_user_01` in commands

### Issue: Token expired error

**Cause:** Refresh token has expired.

**Solution:**
1. Go to https://ACCESS_STAGE_SERVER_ADDRESS/management/api
2. Login with your test user
3. Generate a new refresh token
4. Update the `refresh_token` field in `host_inventory.local.yaml`
5. Tokens typically last 30-90 days depending on what you set during generation

---

## Best Practices

### ✅ DO:

1. **Use descriptive usernames** - `hbi-yourname-test-01`, `hbi-feature-flags-user`, etc.
2. **Document your Org ID** - Keep it in a safe place (password manager)
3. **Cleanup test data** - Delete hosts after testing to avoid clutter
4. **Refresh tokens regularly** - Regenerate before they expire
5. **Share this guide** - Help other team members create their own users
6. **Use unique Org IDs** - Don't share Org IDs between team members

### ❌ DON'T:

1. **Don't commit `host_inventory.local.yaml`** - Contains credentials
2. **Don't share your refresh token** - Treat it like a password
3. **Don't use shared Org IDs for feature flag testing** - Create your own
4. **Don't leave hundreds of test hosts** - Cleanup regularly
5. **Don't reuse the admin user for testing** - Create separate test users
6. **Don't use production credentials** - This guide is for Stage only

---

## Multiple Users in Same Org

You can create multiple test users under the same Org ID for different purposes.

**Example: Adding a second user**

1. In Ethel, add `your-test-user-02` to the same Org ID (`1234567`)
2. Generate a refresh token for the new user at https://ACCESS_STAGE_SERVER_ADDRESS/management/api
3. Update `host_inventory.local.yaml`:

```yaml
stage: &stage
  # ... existing config ...
  users:
    your_test_user_01:
      auth:
        username: "your-test-user-01"
        password: "your-password-here"
        refresh_token: "YOUR_REFRESH_TOKEN_HERE"
      identity:
        account_number: "7654321"
        org_id: "1234567"

    your_test_user_02:  # New user!
      auth:
        username: "your-test-user-02"
        password: "another-password-here"
        refresh_token: "YOUR_REFRESH_TOKEN_HERE"
      identity:
        account_number: "7654321"
        org_id: "1234567"  # Same Org ID
```

Now you can use either user:
```bash
# Use first user
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory create-hosts --user your_test_user_01 -n 10

# Use second user
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory create-hosts --user your_test_user_02 -n 10
```

---

## Reference: Complete IQE Commands

### Create Hosts
```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory create-hosts \
  --user your_test_user_01 \
  -n 50
```

### Create Hosts with Custom Display Name Prefix
```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory create-hosts \
  --user your_test_user_01 \
  -n 10 \
  --display-name-prefix "mytest"
```

### List Hosts (Dry-run Cleanup)
```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory cleanup \
  --user your_test_user_01 \
  --interval 0 \
  --unit days \
  --dry-run
```

### Delete All Hosts
```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory cleanup \
  --user your_test_user_01 \
  --interval 0 \
  --unit days \
  -y
```

### Delete Hosts Older Than 1 Hour
```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory cleanup \
  --user your_test_user_01 \
  --interval 3600 \
  --unit seconds \
  -y
```

### Delete Hosts Older Than 7 Days (Default)
```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory cleanup \
  --user your_test_user_01 \
  -y
```

### Create Hosts via Kafka (Ephemeral Environments)
```bash
iqe host_inventory create-hosts-kafka \
  --user your_test_user_01 \
  -n 10
```

---

## Naming Conventions

To keep the testing environment organized, follow these naming conventions:

### Usernames
- **Admin users:** `[service]-[yourname]-admin`
  - Example: `hbi-jdoe-admin`, `hbi-feature-test-admin`
- **Test users:** `[service]-[yourname]-test-[number]`
  - Example: `hbi-jdoe-test-01`, `hbi-jdoe-test-02`

### Benefits
- Easy to identify who owns which test user
- Clear separation between admin and test users
- Helps with cleanup when users leave the team

---

## Security Notes

### Refresh Token Security

Refresh tokens grant access to your test environment:

1. **Never commit** `host_inventory.local.yaml` to git
2. **Never share** your refresh token in Slack, email, or tickets
3. **Rotate regularly** - regenerate tokens every 30-60 days
4. **Use short expiration** - set tokens to expire in 30-90 days, not years
5. **Revoke immediately** if compromised - regenerate at https://ACCESS_STAGE_SERVER_ADDRESS/management/api

### Access Control

1. Only create test users for **Stage environment** (never Production)
2. Set appropriate expiration on tokens
3. Delete test users in Ethel when no longer needed
4. Audit your Org ID periodically to remove stale hosts

---

## FAQ

### Q: Can I use the same Org ID as my colleague?

**A:** Technically yes, but **not recommended**. The whole point of this setup is isolation. If you share an Org ID, you lose that benefit. Create your own unique Org ID.

### Q: How do I know what my current Org ID is?

**A:** Check Ethel (https://ETHEL_SERVER_ADDRESS) or look at the `org_id` field in your `host_inventory.local.yaml`.

### Q: My token expired, what do I do?

**A:** Go to https://ACCESS_STAGE_SERVER_ADDRESS/management/api, login with your test user, generate a new token, and update `host_inventory.local.yaml`.

### Q: Can I use this for Production environment?

**A:** **NO.** This guide is for **Stage environment only**. Production has different security requirements and approval processes.

### Q: Where does the username/password get used?

**A:** The username/password are used for initial authentication. The `refresh_token` is the primary credential used by IQE for API calls.

### Q: What's the difference between `your_test_user_01` and `your-test-user-01`?

**A:**
- `your_test_user_01` (underscores) - Used as the **key** in the YAML config under `users:`
- `your-test-user-01` (hyphens) - The actual **username** in Ethel and the `auth.username` field

IQE references users by the key name (underscores), while Ethel stores usernames with hyphens.

---

## Related Documentation

- **Ethel User Management:** https://ETHEL_SERVER_ADDRESS
- **Stage Console:** https://CONSOLE_STAGE_SERVER_ADDRESS
- **Stage API Management:** https://ACCESS_STAGE_SERVER_ADDRESS/management/api
- **IQE Framework Documentation:** (Internal Red Hat wiki)
- **Feature Flag Management:** Contact #unleash-support on Slack

---

## Questions?

If you encounter issues not covered in this guide:

1. Check the Troubleshooting section above
2. Ask in #insights-qe Slack channel
3. Contact the HBI team for IQE-specific questions
4. Contact #ethel-support for user creation issues

---

## Appendix: Example Complete Workflow

**Note:** This is a condensed quick-reference guide. All values shown are placeholders - see the main sections above for detailed explanations and security warnings.

Here's a complete example from start to finish:

### 1. Create Admin User in Ethel
- Username: `hbi-jdoe-admin`
- Email: `YOUR_EMAIL_ADDRESS`
- Org ID received: `1234567`
- Account Number: `7654321`

### 2. Create Test User in Ethel
- Username: `hbi-jdoe-test-01`
- Email: `YOUR_EMAIL_ADDRESS`
- Password: `your-password-here`
- Org ID: `1234567` (same as admin)

### 3. Generate Refresh Token
- Login to: https://ACCESS_STAGE_SERVER_ADDRESS/management/api
- Generate token, set 60-day expiration
- Copy token: `YOUR_REFRESH_TOKEN_HERE`

### 4. Create host_inventory.local.yaml
```yaml
stage: &stage
  legacy_hostname: "API_ACCESS_STAGE_SERVER_ADDRESS"
  turnpike_base_url: "https://MTLS_CONSOLE_SERVER_ADDRESS/api/rbac"
  default_user: hbi_jdoe_test_01
  org_admin_user: hbi_jdoe_test_01
  secondary_user: hbi_jdoe_test_01
  frontend_user: hbi_jdoe_test_01
  users:
    hbi_jdoe_test_01:
      auth:
        username: "hbi-jdoe-test-01"
        password: "your-password-here"
        refresh_token: "YOUR_REFRESH_TOKEN_HERE"
      identity:
        account_number: "7654321"
        org_id: "1234567"

stage_proxy: *stage
```

### 5. Test
```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory create-hosts -n 5 --user hbi_jdoe_test_01
```

### 6. Cleanup
```bash
ENV_FOR_DYNACONF=stage_proxy iqe host_inventory cleanup --user hbi_jdoe_test_01 -y
```

---

**Document Status:** Active
**Maintained By:** Insights HBI QE Team
**Last Verified:** 2026-04-01
