// set 'development' or 'production'
const ENVIRONMENT = 'production';

// Dev environments URLs
const devConfig = {
  API_URL: 'http://localhost:8000',
  IMAGES_BASE_URL: 'http://localhost:8000/images'
};

// Prod environments URLs
const prodConfig = {
  API_URL: 'http://sunscan.local:8000',
  IMAGES_BASE_URL: 'http://sunscan.local:8000/images'
};

// active config
const activeConfig = ENVIRONMENT === 'production' ? prodConfig : devConfig;

export const config = {
  // Mode dev
  isDev: ENVIRONMENT === 'development',
  
  // actual environment
  environment: ENVIRONMENT,
  //
  ...activeConfig,
  
  // dev mode configs
  dev: {
    enableLogs: true,           // Activelogs 
    mockAPI: false,             // Active/desactivate mockAPI
    delaySimulation: 0,         // Simulation delay
    showDebugInfo: true,        // Debug info
  }
};

// dev logs helper
export const devLog = (...args) => {
  if (config.isDev && config.dev.enableLogs) {
    console.log(`[${config.environment}]`, ...args);
  }
}; 