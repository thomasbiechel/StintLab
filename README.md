# StintLab 🏁

Formula 1 race data, explained — one question per session.

StintLab turns raw timing and telemetry data into focused analyses:
long-run pace in practice, where time was lost in qualifying,
and how stints and strategies played out in the race.
Each analysis is published as an Instagram carousel ([@stint_lab](https://www.instagram.com/stint_lab/))
and documented here with its method and limitations.

## Structure

- `stintlab/` — reusable analysis and plotting modules
- `posts/` — one folder per published analysis (script, slides, write-up)

## Data

Timing and telemetry data from OpenF1.
Not affiliated with Formula 1, the FIA or any team.

## Requirements

Python 3.11+ and an OpenF1 account (for authenticated API access).

## Setup

    git clone https://github.com/thomasbiechel/StintLab.git
    cd StintLab
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    copy .env.example .env      # then add your OpenF1 username and password

## Usage

Each post is described by a `post.toml` (session, drivers, analyses, titles):

    python make_post.py posts/2026-madrid/post.toml

Data is loaded from OpenF1 once and cached in `data/cache/`.
Before rendering, a plausibility check compares the plotted gaps
against OpenF1 position data.

## Tests

    python -m pytest

## Author

Thomas Biechel · Mechanical/Automotive Engineering student, Hochschule München
