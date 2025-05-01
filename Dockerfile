# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install ffmpeg and espeak-ng
RUN apt-get update && apt-get install -y ffmpeg espeak-ng && apt-get clean

# Copy the rest of the application
COPY . .

# Expose port explicitly
EXPOSE 10000

# Command to run the application with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--timeout", "120", "app:app"]
