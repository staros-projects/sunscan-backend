# Webapp Gallery for Sunscan

## Features

### Scans
- List all scans by date
- View scan images with zoom and rotation
- Multiple scan download selection
- Delete scans
- View scan logs

### Stacking
- List stacked images
- View stacking results
- Download stacked images
- Delete stacking folders

### Animations
- List solar animations
- View animation sequences
- Download animations
- Delete animation folders

### System
- Storage usage monitoring
- Camera information
- Server version

## Environment Configuration

The environment (development or production) is configured directly in the `src/config.js` file:

```javascript
// Modify this line to change environment
const ENVIRONMENT = 'development'; // or 'production'
```

### For Development
    
```bash
npm install 
npm run dev
```

### For Production

1. In `src/config.js`, change the environment to production:
```javascript
const ENVIRONMENT = 'production';
```

2. Build the application:
```bash
npm run build
```

## Important
- The Sunscan server must be running on port 8000
- Since the Sunscan server is not connected to the internet during use, make sure all dependencies are installed locally and not fetched from the internet

## URL Configuration

URLs for each environment can be modified in `src/config.js`:

```javascript
// Development configuration
const devConfig = {
  API_URL: 'http://localhost:8000',
  IMAGES_BASE_URL: 'http://localhost:8000/images'
};

// Production configuration
const prodConfig = {
  API_URL: 'http://sunscan.local:8000',
  IMAGES_BASE_URL: 'http://sunscan.local:8000/images'
};
```

# Important
Sunscan server is running on IP:8000, so make sure to run the server before running the webapp.
Sunscan server is not connected to internet when is used, make sure the webapp libs are installed in the server and not fetched from internet.  


