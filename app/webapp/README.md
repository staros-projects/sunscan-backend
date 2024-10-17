# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh


### For dev start
    
```bash
npm install 
npm run dev
```
## For Prod
```bash
npm run build
# go to dist folder
```

# Important
Sunscan server is running on IP:8000, so make sure to run the server before running the webapp.
Sunscan server is not connected to internet when is used, make sure the webapp libs are installed in the server and not fetched from internet.  
