# How to obtain Strava API Credentials:
To enable Strava integration, you need to create a developer application and generate a long-lived Refresh Token:

1. **Create an App**: Go to the [Strava Settings API](https://www.strava.com/settings/api) and create an application (set "Localhost" as the Authorization Callback Domain).
2. **Get Client ID & Secret**: Note down your `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET`.
3. **Authorize and Get Code**: Paste the following URL in your browser (replace `YOUR_CLIENT_ID` with your actual ID):
   `https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=read,activity:read_all`
4. **Exchange Code for Refresh Token**: Click "Authorize", then copy the `code` parameter from the URL of the resulting blank page. Use this command in your terminal to get the final `STRAVA_REFRESH_TOKEN`:
   ```bash
   curl -X POST [https://www.strava.com/oauth/token](https://www.strava.com/oauth/token) \
     -d client_id=YOUR_CLIENT_ID \
     -d client_secret=YOUR_CLIENT_SECRET \
     -d code=YOUR_CODE_FROM_URL \
     -d grant_type=authorization_code
   ```