# Ammo Tracker CH 🎯

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

A turnkey, Docker-based tool for automated tracking and visualization of ammunition prices (1000-round bulk) across various Swiss online shops.

<img width="2686" height="1590" alt="image" src="https://github.com/user-attachments/assets/1b0783c5-dea9-454b-8b07-0485f545f381" />

## ✨ Features

- **Automated Price Tracking**: Hybrid-Scraping fetches prices daily at 04:00 AM in fractions of a second using cached CSS selectors.
- **Smart AI Fallback**: When shop layouts change, the tool automatically uses the Google Gemini API to analyze HTML and generate new selectors.
- **Autonomous Scout**: Every 14 days, an AI scout autonomously searches for new Swiss gun shops and adds them to the system.
- **Beautiful UI**: Fast, minimalist frontend with a modern glassmorphism design and interactive price history charts.
- **Admin Panel**: Easily add new URLs to track directly from the web interface.

## 🏗️ Architecture

- **Frontend (Nginx)**: Built with Vanilla JS and Chart.js for data visualization.
- **Backend (Python/FastAPI)**: Background worker managing the Fast-Track (cached selectors) and Slow-Track (Gemini API) scraping logic.

## 📋 Prerequisites

- **Docker & Docker Compose**: Must be installed on your host machine.
- **Google Gemini API Key**: Required for the AI fallback and Auto-Scout features (you can get a free tier key from Google AI Studio).

## 🚀 Getting Started

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/ammotracker-ch.git
   cd ammotracker-ch
   ```

2. **Set Environment Variables**:
   Copy the `.env.example` template to a new file named `.env`:
   ```bash
   cp .env.example .env
   ```
   Add your actual `GEMINI_API_KEY` to the `.env` file. You can optionally change the `ADMIN_PASSWORD` (default is `changeme`).

3. **Start Docker Compose**:
   Launch the application in the background:
   ```bash
   docker-compose up -d --build
   ```

4. **Access the Application**:
   Open your web browser and navigate to `http://localhost:8081`.
   > **Note:** The first scraping run starts automatically in the background when the container spins up. It may take a few minutes before data appears in the table.

## ⚙️ Admin Panel

You can expand the admin panel by clicking the **"Admin"** button in the top right corner of the web interface. 
Here, using your `ADMIN_PASSWORD`, you can add new URLs for Swiss gun shops. The URLs are permanently stored in the `urls.json` file on the shared volume.

## 💾 Data & Persistence

All generated data (price JSONs, shop URLs) is stored in the `shared-data` Docker volume (`/app/data`). This ensures that your data remains persistent even after restarting or updating the containers.

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.
