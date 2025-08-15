# OAuth Setup Guide

PaperSorter supports authentication via Google OAuth, GitHub OAuth, and ORCID OAuth. You can configure any combination of these providers. ORCID is particularly recommended for academic websites as it provides unique researcher identifiers.

## Configuration Structure

OAuth settings are configured in `config.yml` under the following structure:

```yaml
web:
  flask_secret_key: "your-secret-key"  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
  base_url: "https://yourdomain.com"   # Your application's base URL

oauth:
  google:
    client_id: "your-client-id.apps.googleusercontent.com"
    secret: "your-client-secret"
  github:
    client_id: "your-github-client-id"
    secret: "your-github-client-secret"
  orcid:
    client_id: "APP-XXXXXXXXXXXX"
    secret: "your-orcid-client-secret"
    sandbox: false  # Set to true for testing with sandbox.orcid.org
```

## Google OAuth Setup

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google+ API for your project

### 2. Configure OAuth Consent Screen

1. In the Google Cloud Console, go to "APIs & Services" > "OAuth consent screen"
2. Choose "External" user type (unless you're using Google Workspace)
3. Fill in the required information:
   - App name: PaperSorter
   - User support email: Your email
   - Developer contact information: Your email
4. Add scopes: `openid`, `email`, `profile`
5. Save and continue

### 3. Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. Choose "Web application" as the application type
4. Add authorized redirect URIs:
   - `http://localhost:5001/callback` (for development)
   - `https://yourdomain.com/callback` (for production)
5. Save the credentials and copy the Client ID and Client Secret

## GitHub OAuth Setup

### 1. Create a GitHub OAuth App

1. Go to GitHub Settings > Developer settings > [OAuth Apps](https://github.com/settings/developers)
2. Click "New OAuth App"
3. Fill in the application details:
   - Application name: PaperSorter
   - Homepage URL: `https://yourdomain.com` (or `http://localhost:5001` for development)
   - Authorization callback URL:
     - `http://localhost:5001/callback/github` (for development)
     - `https://yourdomain.com/callback/github` (for production)
4. Click "Register application"

### 2. Get Client Credentials

1. After creating the app, you'll see your Client ID
2. Click "Generate a new client secret"
3. Copy the Client ID and Client Secret immediately (the secret won't be shown again)

## ORCID OAuth Setup

ORCID provides persistent digital identifiers for researchers, making it ideal for academic applications.

### 1. Register Your Application

#### For Production (orcid.org):
1. Go to [ORCID Developer Tools](https://orcid.org/developer-tools)
2. Sign in with your ORCID account
3. Click "Register a public API client"
4. Fill in the application details:
   - Application name: PaperSorter
   - Application website: `https://yourdomain.com`
   - Description: Academic paper recommendation system
   - Redirect URIs:
     - `https://yourdomain.com/callback/orcid` (for production)
     - `http://localhost:5001/callback/orcid` (for development)
5. Save the application

#### For Testing (sandbox.orcid.org):
1. Go to [ORCID Sandbox](https://sandbox.orcid.org/developer-tools)
2. Create a sandbox account if you don't have one
3. Follow the same steps as production
4. Set `sandbox: true` in your configuration

### 2. Get Client Credentials

1. After registration, you'll receive:
   - Client ID (format: APP-XXXXXXXXXXXX)
   - Client Secret
2. Save these credentials securely

### 3. Configuration Notes

- ORCID uses the `/authenticate` scope for basic sign-in
- Users are identified by their ORCID iD (XXXX-XXXX-XXXX-XXXX format)
- The system stores users as `ORCID-ID@orcid.org` in the database
- No email address is required (ORCID iD serves as the unique identifier)

## Configuration File Setup

### 1. Create or Update config.yml

Add the OAuth configuration to your `config.yml` file:

```yaml
# Database configuration
db:
  type: postgres
  host: localhost
  database: papersorter
  user: papersorter
  password: "your-db-password"

# Web configuration
web:
  flask_secret_key: "your-generated-secret-key"
  base_url: "https://yourdomain.com"

# OAuth configuration (configure one or more providers)
oauth:
  google:
    client_id: "your-client-id.apps.googleusercontent.com"
    secret: "your-google-client-secret"
  github:
    client_id: "your-github-client-id"
    secret: "your-github-client-secret"
  orcid:
    client_id: "APP-XXXXXXXXXXXX"
    secret: "your-orcid-client-secret"
    sandbox: false  # Set to true for sandbox.orcid.org testing
```

### 2. Generate Flask Secret Key

Generate a secure secret key for Flask sessions:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Running the Application

After configuring OAuth:

```bash
papersorter serve
```

Navigate to `http://localhost:5001` and you should see login options for the configured OAuth providers.

## Backward Compatibility

The system maintains backward compatibility with older configuration formats:

```yaml
# Old format (still supported)
google_oauth:
  client_id: "your-client-id"
  secret: "your-client-secret"
  flask_secret_key: "your-secret-key"

# Note: github_oauth format is no longer supported
# Use the oauth.github format shown above
```

## Security Best Practices

1. **Never commit credentials to version control**
   - Add `config.yml` to `.gitignore`
   - Use environment-specific configuration files

2. **Use HTTPS in production**
   - OAuth redirects require secure connections
   - Protects session cookies from interception

3. **Rotate credentials regularly**
   - Change OAuth client secrets periodically
   - Update Flask secret key if compromised

4. **Restrict OAuth app permissions**
   - Only request necessary scopes
   - For GitHub: only `user:email` scope is needed
   - For Google: only `openid`, `email`, `profile` are needed

## Troubleshooting

### "Authentication failed" Error

**For Google OAuth:**
- Verify redirect URI exactly matches: `https://yourdomain.com/callback`
- Check that Google+ API is enabled in your project
- Ensure client ID and secret are correctly copied

**For GitHub OAuth:**
- Verify callback URL exactly matches: `https://yourdomain.com/callback/github`
- Check that the OAuth app is not in suspended state
- Ensure client ID and secret are correctly copied

**For ORCID OAuth:**
- Verify callback URL exactly matches: `https://yourdomain.com/callback/orcid`
- Check you're using the correct environment (production vs sandbox)
- Ensure the `sandbox` configuration matches your ORCID registration
- Client ID should start with "APP-" followed by alphanumeric characters

### "No email associated with GitHub account" Error

- The user's GitHub account must have a verified email address
- The email can be private, but must be verified
- Check GitHub Settings > Emails to verify email status

### Users Not Persisting Between Sessions

- Verify PostgreSQL database is properly configured
- Check that the `users` table exists with correct schema
- Ensure database write permissions are set correctly
- Verify `web.flask_secret_key` is set and consistent across restarts

### "No ORCID iD found" Error

- This usually indicates an issue with the ORCID OAuth response
- Verify your application is properly registered with ORCID
- Check that redirect URIs are correctly configured in ORCID developer tools

### Multiple OAuth Providers Not Showing

- Ensure all desired providers are configured in `config.yml`
- Check application logs for configuration errors
- Verify that client IDs and secrets are present for each provider
- ORCID client IDs starting with "APP-" are filtered out as example values

## Database Schema

OAuth users are stored in the `users` table with the following relevant fields:

- `username`: The user's identifier from OAuth provider
  - Google/GitHub: Email address
  - ORCID: ORCID iD formatted as `XXXX-XXXX-XXXX-XXXX@orcid.org`
- `password`: Set to "oauth" for OAuth users
- `lastlogin`: Automatically updated on login and during active sessions (throttled to every 10 minutes)
- `created`: Timestamp of first login
- `is_admin`: Admin status (default: false, can be auto-promoted via config on login)

## Managing Admin Privileges

### Automatic Admin Promotion via Configuration (Recommended)

Add users to the `admin_users` list in your `config.yml`. Users in this list are automatically promoted to admin on login:

```yaml
# config.yml
admin_users:
  # Email addresses for Google/GitHub OAuth
  - "admin@example.com"
  - "researcher@university.edu"
  # ORCID identifiers (must include @orcid.org suffix)
  - "0000-0002-1825-0097@orcid.org"
  - "0000-0003-4567-8901@orcid.org"
```

Important notes about this approach:
- Users in the list are automatically promoted to admin on login
- **The list only promotes, never demotes** - existing admins remain admins even if not in the list
- To revoke admin privileges, use the web interface or database updates
- Useful for ensuring specific users always have admin access
- No database access required for initial setup

### Manual Admin Assignment

#### Via Web Interface
Administrators can manage user privileges through Settings → Users in the web interface.

#### Via Database
For immediate changes without waiting for the next login:

```sql
-- For email-based providers (Google, GitHub)
UPDATE users SET is_admin = true WHERE username = 'admin@example.com';

-- For ORCID users
UPDATE users SET is_admin = true WHERE username = '0000-0002-1825-0097@orcid.org';
```

Note: Admin privileges set via database are permanent unless explicitly revoked. The `admin_users` list only promotes users, never demotes them.