# Google OAuth Setup Guide

To enable Google OAuth authentication for PaperSorter, follow these steps:

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google+ API for your project

## 2. Configure OAuth Consent Screen

1. In the Google Cloud Console, go to "APIs & Services" > "OAuth consent screen"
2. Choose "External" user type (unless you're using Google Workspace)
3. Fill in the required information:
   - App name: PaperSorter
   - User support email: Your email
   - Developer contact information: Your email
4. Add scopes: `openid`, `email`, `profile`
5. Save and continue

## 3. Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. Choose "Web application" as the application type
4. Add authorized redirect URIs:
   - `http://localhost:5001/callback` (for development)
   - `https://yourdomain.com/callback` (for production)
5. Save the credentials

## 4. Set Environment Variables

Set the following environment variables before running the application:

```bash
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export FLASK_SECRET_KEY="your-secret-key"  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
```

You can also add these to a `.env` file in the project root:

```env
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
FLASK_SECRET_KEY=your-secret-key
```

## 5. Run the Application

After setting up the environment variables:

```bash
papersorter serve
```

## Security Notes

- Never commit your OAuth credentials to version control
- Use HTTPS in production
- Keep your Flask secret key secure and unique
- Regularly rotate your credentials

## Troubleshooting

### "Authentication failed" error
- Check that your redirect URI exactly matches what's configured in Google Cloud Console
- Ensure your client ID and secret are correct
- Check that the Google+ API is enabled

### Users not persisting
- Verify your PostgreSQL database is properly configured
- Check that the users table exists with the correct schema
- Ensure database write permissions are set correctly