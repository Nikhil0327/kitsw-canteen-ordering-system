# Use Python 3.11 to avoid SQLAlchemy + TypingOnly crash
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy your project folder
COPY canteen-project/ ./canteen-project

# Copy requirements file
COPY canteen-project/requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Set environment variables
ENV FLASK_APP=canteen-project/app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production

# Expose port 5000 (Flask default)
EXPOSE 5000

# Run the app
CMD ["python", "canteen-project/app.py"]
