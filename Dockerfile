# Dockerfile - Fixed with matching Chrome and ChromeDriver versions
FROM python:3.10-slim

# Install Chrome and dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome 120 (matches ChromeDriver 120)
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable=120.0.6099.109-1 \
    && apt-mark hold google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver 120 (matching Chrome version)
RUN wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.109/linux64/chromedriver-linux64.zip" \
    && unzip chromedriver-linux64.zip \
    && chmod +x chromedriver-linux64/chromedriver \
    && mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rm -rf chromedriver-linux64.zip chromedriver-linux64

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p static uploads

EXPOSE 8080
CMD ["python", "app.py"]