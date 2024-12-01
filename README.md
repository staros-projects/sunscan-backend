# Sunscan Backend

This repository contains the official backend for the Sunscan project, a revolutionary solar imaging and analysis tool.

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi) ![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)

## Description

Sunscan is a spectroheliograph designed to capture images of the Sun in minutes, directly from a smartphone. This complete and autonomous device is the result of several months of work by the STAROS team (Guillaume Bertrand, Christian Buil, Valérie Desnoux, Olivier Garde, Matthieu Le Lain).

The Sunscan backend provides server-side functionality for the Sunscan application. It handles image processing, data management, and serves as the API for the frontend application.

## Features

- Control Sunscan via smartphone or tablet
- Capture solar images showing prominences, flares, and sunspots
- Intuitive interface requiring no special knowledge
- Server-side image processing and data management

## Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/your-username/sunscan-backend.git
   cd sunscan-backend
   ```

2. Create a virtual environment (optional but recommended):
   ```
   python -m venv --system-site-packages venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```
   sudo apt-get install gcc python3-dev
   sudo apt-get install -y libcap-dev libcamera-dev python3-libcamera python3-pyqt5 python3-prctl libatlas-base-dev ffmpeg
   pip install -r app/requirements.txt
   sudo apt-get install uvicorn
   ```

## Configuration

1. Copy the example configuration file:
   ```
   cp config.example.py config.py
   ```

2. Edit `config.py` to set up your specific configuration parameters if needed.

## Running the Server

The Sunscan backend is a FastAPI application that uses Uvicorn as the ASGI server.

To start the backend server:

1. Ensure you're in the project directory and your virtual environment is activated (if you're using one).

2. Run the following command:
   ```
   cd app
   python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

   ```

   This command does the following:
   - `app.main` refers to the `main.py` file in the `app` directory
   - `:app` refers to the FastAPI instance in the `main.py` file
   - `--reload` enables auto-reloading, which is useful during development

   ```
   # or just launch the start script
   ./start.sh
   ```

3. The server should start and display a message indicating it's running, along with the address and port (e.g., "Uvicorn running on http://127.0.0.1:8000").

4. You can now access the API endpoints using this address.

Note: Make sure all required environment variables are set and the database is properly configured before starting the server. Refer to the configuration section for more details.

## Hotspot

Configure the hotspot by the script:
```
sudo  system/usr/local/bin/configure_hotspot.sh
```


## Mobile Application

An open-source mobile application, built using Expo, is currently under development to control the Sunscan instrument. You can find the application repository at: [https://github.com/staros-projects/sunscan-app](https://github.com/staros-projects/sunscan-app)

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are greatly appreciated.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is distributed under the GPLv3 License. See `LICENSE` file for more information.
