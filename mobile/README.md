# Lulu Line mobile client

This is the source for a real Android/iOS installable client, not a PWA or home-screen shortcut. Capacitor generates native Android and iOS projects around the existing secure HTTPS application.

## Security

- The production server URL is injected at build time through the protected `LLCC_SERVER_URL` GitHub Actions secret.
- HTTP, embedded credentials, and mixed content are rejected.
- No passwords, API keys, database credentials, or live business data belong in this directory.
- Production distribution must use Lulu Line's Android signing key and Apple Developer signing identity.

## Local build

Install Node.js 20+, then set `LLCC_SERVER_URL` to the HTTPS deployment and run:

```bash
npm ci
npm run configure
npx cap add android
npx cap add ios
npm run sync
```

Use Android Studio for signed APK/AAB builds and Xcode for iOS signing/archive. CI produces an unsigned debug APK automatically; store release builds require signing secrets.
