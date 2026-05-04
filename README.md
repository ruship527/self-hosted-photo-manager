## Project Status

This project is currently under active development. Core features such as photo uploads, file uploads, previews, downloads, album organization, metadata storage, and AI image tagging have been implemented.

Future updates will focus on improving authentication, UI polish, search/filtering, mobile responsiveness, and deployment reliability.

# Self-Hosted Photo & File Management App

A self-hosted web application for uploading, organizing, previewing, downloading, and managing photos and files.  
The project was built with a FastAPI backend and a simple browser-based frontend, then deployed on an Ubuntu homelab server using Docker.

## Overview

This project was created as a personal self-hosted alternative to basic cloud photo and file storage. It allows users to upload photos and documents, view them through a web interface, organize photos into albums, and use AI-generated tags to help identify uploaded images.

The project also served as hands-on experience with backend development, Linux server deployment, Docker containers, file storage, database design, and debugging real deployment issues.

## Features

- Upload photos and general files through a web interface
- Preview uploaded photos in a gallery layout
- Preview supported files from the browser
- Download uploaded photos and files
- Delete uploaded photos and files
- Organize photos into albums
- Store metadata such as:
  - Original filename
  - Saved filename
  - Upload date
  - Photo taken date
  - File hash
  - AI-generated tags
- Detect duplicate uploads using file hashing
- Generate AI tags for uploaded images
- Backend database storage using SQLAlchemy
- Docker-based deployment
- Designed to run on a self-hosted Ubuntu server

## Tech Stack

### Backend
- Python
- FastAPI
- SQLAlchemy
- SQLite
- Alembic
- Pillow
- Transformers

### Frontend
- HTML
- CSS
- JavaScript

### Deployment / Infrastructure
- Docker
- Docker Compose
- Ubuntu Server
- Linux file permissions
- SSH/SCP
- Port mapping and volume mounts

## Project Structure

```text
Photoapp/
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── routes/
│   │   │   ├── albums.py
│   │   │   ├── auth.py
│   │   │   ├── files.py
│   │   │   ├── photos.py
│   │   │   └── stats.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── utils.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── retag_photos.py
├── frontend/
│   ├── album_detail.html
│   ├── albums.html
│   ├── files.html
│   ├── index.html
│   ├── login.html
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── .gitignore
└── README.md
